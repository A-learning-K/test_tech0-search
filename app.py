"""
app.py — Tech0 Search v1.0（完成版）
Streamlit アプリ本体。検索・クローラー・一覧の3タブ構成。
"""

import re
import streamlit as st

# --- 投稿機能で必要 ----
import datetime
import pandas as pd
# -----

# Hotタブで利用
import urllib.parse

from database import init_db, get_all_pages, insert_page, log_search
from ranking import get_engine, rebuild_index
from crawler import crawl_url

# アプリ起動時に DB を初期化する（テーブルが未作成なら作る）
init_db()

st.set_page_config(
    page_title="Tech0 Search v1.0",
    page_icon="🔍",
    layout="wide"
)

# ── キャッシュ付きインデックス構築 ─────────────────────────────
@st.cache_resource
def load_and_index():
    """全ページを DB から読み込み TF-IDF インデックスを構築する。
    @st.cache_resource により、アプリ起動中は一度だけ実行される。"""
    pages = get_all_pages()
    if pages:
        rebuild_index(pages)
    return pages

pages = load_and_index()
engine = get_engine()

# ── ヘッダー ──────────────────────────────────────────────────
st.title("🔍 Tech0 Search v1.0")
st.caption("PROJECT ZERO — 社内ナレッジ検索エンジン【TF-IDFランキング搭載】")

with st.sidebar:
    st.header("DB の状態")
    st.metric("登録ページ数", f"{len(pages)} 件")
    if st.button("🔄 インデックスを更新"):
        st.cache_resource.clear()
        st.rerun()

# ── タブ ──────────────────────────────────────────────────────
tab_search, tab_crawl, tab_list, tab_post, tab_hot = st.tabs(
    ["🔍 検索", "🤖 クローラー", "📋 一覧", "💡 投稿 ", "🔥 Hot"]
)

# ── 検索タブ ───────────────────────────────────────────────────
with tab_search:
    st.subheader("キーワードで検索")

    col_search, col_options = st.columns([3, 1])
    with col_search:
        query = st.text_input("🔍 キーワードを入力", placeholder="例: DX, IoT, 製造業",
                              label_visibility="collapsed")
    with col_options:
        top_n = st.selectbox("表示件数", [10, 20, 50], index=0)

    if query:
        results = engine.search(query, top_n=top_n)
        log_search(query, len(results))    # 検索するたびに自動記録（Step7で実装予定）

        st.markdown(f"**📊 検索結果：{len(results)} 件**（TF-IDFスコア順）")
        st.divider()

        if results:
            for i, page in enumerate(results, 1):
                with st.container():
                    col_rank, col_title, col_score = st.columns([0.5, 4, 1])
                    with col_rank:
                        # 上位3件にはメダルを表示する
                        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else str(i)
                        st.markdown(f"### {medal}")
                    with col_title:
                        st.markdown(f"### {page['title']}")
                    with col_score:
                        # relevance_score（最終スコア）と base_score（TF-IDFのみ）を両方表示
                        st.metric("スコア", f"{page['relevance_score']}",
                                  delta=f"基準: {page['base_score']}")

                    desc = page.get("description", "")
                    if desc:
                        st.markdown(f"*{desc[:200]}{'...' if len(desc) > 200 else ''}*")

                    kw = page.get("keywords", "") or ""
                    if kw:
                        kw_list = [k.strip() for k in kw.split(",") if k.strip()][:5]
                        tags = " ".join([f"`{k}`" for k in kw_list])
                        st.markdown(f"🏷️ {tags}")

                    col1, col2, col3, col4 = st.columns(4)
                    with col1: st.caption(f"👤 {page.get('author', '不明') or '不明'}")
                    with col2: st.caption(f"📊 {page.get('word_count', 0)} 語")
                    with col3: st.caption(f"📁 {page.get('category', '未分類') or '未分類'}")
                    with col4: st.caption(f"📅 {(page.get('crawled_at', '') or '')[:10]}")

                    st.markdown(f"🔗 [{page['url']}]({page['url']})")
                    st.divider()
        else:
            st.info("該当するページが見つかりませんでした")

# ── クローラータブ ─────────────────────────────────────────────
if "crawl_results" not in st.session_state:
    st.session_state.crawl_results = []

with tab_crawl:
    st.subheader("🤖 自動クローラー")
    st.caption("URLを入力してクロールし、インデックスに登録する")

    crawl_url_input = st.text_area(
        "クロール対象URL",
        placeholder="URLを改行またはスペース区切りで入力してください",
        height=150
    )

    if st.button("🤖 クロール実行", type="primary"):
        if crawl_url_input:
            raw_parts = re.split(r'[\s]+', crawl_url_input.strip())
            urls = [p for p in raw_parts if p.startswith(("http://", "https://"))]

            if not urls:
                st.error("有効なURLが見つかりませんでした")
            else:
                st.write(f"🔗 {len(urls)}件のURLを処理します")

                st.session_state.crawl_results = []

                for url in urls:
                    with st.spinner(f"クロール中: {url}"):
                        result = crawl_url(url)

                    if result and result.get('crawl_status') == 'success':
                        st.success(f"✅ 成功: {url}")

                        col1, col2 = st.columns(2)
                        with col1:
                            title = result.get('title', '')
                            st.metric("📄 タイトル", (title[:30] + "...") if len(title) > 30 else title)
                        with col2:
                            st.metric("📊 文字数", f"{result.get('word_count', 0)}語")

                        st.session_state.crawl_results.append(result)
                    else:
                        st.error(f"❌ 失敗: {url}")

    if st.session_state.crawl_results:
        st.info(f"{len(st.session_state.crawl_results)}件のクロール結果を登録できます。")

        if st.button("💾 全てインデックスに登録"):
            total = len(st.session_state.crawl_results)

            progress_text = st.empty()
            progress_bar = st.progress(0)

            for i, r in enumerate(st.session_state.crawl_results, start=1):
                progress_text.write(f"📥 {i} / {total} 件登録中...")
                insert_page(r)
                progress_bar.progress(i / total)

            progress_text.write(f"✅ {total} / {total} 件 登録完了！")
            st.success(f"{total}件 登録完了！")
            st.session_state.crawl_results = []
            st.cache_resource.clear()
            st.rerun()

# ── 一覧タブ ───────────────────────────────────────────────────
with tab_list:
    st.subheader(f"📋 登録済みページ一覧（{len(pages)} 件）")
    if not pages:
        st.info("登録されているページがありません。クローラータブからページを追加してください。")
    else:
        for page in pages:
            with st.expander(f"📄 {page['title']}"):
                st.markdown(f"**URL：** {page['url']}")
                st.markdown(f"**説明：** {page.get('description', '（なし）') or '（なし）'}")
                col1, col2, col3 = st.columns(3)
                with col1: st.caption(f"語数：{page.get('word_count', 0)}")
                with col2: st.caption(f"作成者：{page.get('author', '不明') or '不明'}")
                with col3: st.caption(f"カテゴリ：{page.get('category', '未分類') or '未分類'}")

# ── 投稿タブ ───────────────────────────────────────────────────
with tab_post:
    
        
    # お呼び出し閾値（デモ用に低め設定）
    OYOBIDASHI_THRESHOLD = 3  # 本番は100
    
    # お呼び出しフラグ { post_index: True/False }
    if "oyobidashi_flags" not in st.session_state:
        st.session_state["oyobidashi_flags"] = {}
    

     # ── お呼び出し通知（フラグが立っていたら一番上に表示） ──
    for post_index, flagged in list(st.session_state["oyobidashi_flags"].items()):
        if not flagged:
            continue

        # 対象の投稿を取得する
        post = posts[post_index]

        with st.container(border=True):
            st.markdown("##### 📣 黒崎からのお呼び出し")
            st.caption("黒崎 誠一郎　執行役員 / 経営企画担当")
            st.write("あなたの提案に注目しています。")
            st.write("詳しくお話を聞かせてください。")
            st.write("下記の日時に私の部屋までお越しください。")

            # 日時カード
            with st.container(border=True):
                st.write("🗓　12月5日（木）14:00")
                st.caption("黒崎執行役員室（本館5F）")

            # 対象投稿
            with st.container(border=True):
                st.caption("対象スレッド")
                st.write(post["commeent"][:40] + "…")

            # 返答ボタン
            col1, col2 = st.columns(2)
            with col1:
                if st.button("後で確認する", key=f"later_{post_index}"):
                    # フラグを折りたたんで通知を非表示にする
                    st.session_state["oyobidashi_flags"][post_index] = False
                    st.rerun()
            with col2:
                if st.button("承知しました ✓", key=f"accept_{post_index}"):
                    # フラグを消して通知を非表示にする
                    st.session_state["oyobidashi_flags"][post_index] = False
                    st.success("承知しました！当日お伺いします。")
                    st.rerun()

    st.divider()

    # ── 投稿フォーム ──────────────────────────────────────────
    with st.form("post_form", clear_on_submit=True):
        comment = st.text_area("投稿", placeholder="アイデアを書いてみよう")
        anonymous = st.checkbox("匿名で投稿する")
        submitted = st.form_submit_button("投稿する")
        
        if submitted:
            if not comment.strip():
                st.warning("投稿を入力してください")
            else:
                # save_posts(name, comment)　投稿処理が飛ぶ
                st.success("投稿しました")
    
    st.divider()

    # ── 投稿一覧 ──────────────────────────────────────────
    # posts = get_all_posts()  # DBから取得予定
    posts = [
        {"commeent": "ライン3の待機電力を削減すれば年間200万円のコスト削減が見込めるのでは？", "name": "田中太郎", "anonymous": True, "good": 10},
        {"commeent": "新人研修の座学を減らしてOJT中心に変えた方がいいかも？", "name": "浦島太郎", "anonymous": False ,"good": 20},
        {"commeent": "外注している部品加工を内製化するとコスト3割減になる", "name": "百田桃太郎", "anonymous": True, "good": 1},
    ]

    st.subheader(f"📋 投稿一覧（{len(posts)} 件）")
    if not posts:
        st.info("投稿はありません。最初のアイデアを投稿してみましょう💡")
    else:
        for post in posts:
            if post["anonymous"]:
                name = "匿名ユーザー"
            else:
                name = post["name"]

            with st.container(border=True):
                st.write(f"{post['commeent']}")
                st.write(f"投稿者：{name}")
                st.write(f"👍いいね数：{post['good']}")

# ── Hotタブ ───────────────────────────────────────────────────
with tab_hot:

    # ── 投稿一覧 ──────────────────────────────────────────
    # posts = get_all_posts()  # DBから取得予定

    post_top10 = sorted(posts, key=lambda x: x["good"], reverse=True)[:10]

    st.subheader(f"📋 今話題の投稿")
    if not posts:
        st.info("投稿はありません。最初のアイデアを投稿してみましょう💡")
    else:
        for post in post_top10:
            if post["anonymous"]:
                name = "匿名ユーザー"
            else:
                name = post["name"]

            # お呼び出しボタン（閾値を超えた投稿のみ表示）
            if post["good"] >= OYOBIDASHI_THRESHOLD:
                st.divider()
                # 対象投稿のインデックスを特定する
                post_index = posts.index(post)
                already_sent = st.session_state["oyobidashi_flags"].get(post_index, False)

            if already_sent:
                st.success("📣 お呼び出し済み")
            else:
                if st.button("📣 お呼び出しを送る", key=f"hot_oyobidashi_{post_index}"):
                    # フラグを立てる
                        st.session_state["oyobidashi_flags"][post_index] = True
                        st.toast("お呼び出しを送りました", icon="📣")
                        st.rerun()
                

st.divider()
st.caption("© 2025 PROJECT ZERO — Tech0 Search v1.0 | Powered by TF-IDF")
