import streamlit as st
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
import firebase_admin
from firebase_admin import credentials, firestore
import sys
import ast

# Firestore 初期化
if not firebase_admin._apps:
    try:
        firebase_creds = st.secrets["firebase"]
        if isinstance(firebase_creds, str):
            firebase_creds = ast.literal_eval(firebase_creds)
        elif not isinstance(firebase_creds, dict):
            firebase_creds = dict(firebase_creds)
        cred = credentials.Certificate(firebase_creds)
    except KeyError:
        cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

# キャッシュを用いた Firestore アクセス
@st.cache_resource(ttl=10)
def fetch_all_questions():
    return list(db.collection("questions").order_by("timestamp", direction=firestore.Query.DESCENDING).stream())

@st.cache_resource(ttl=10)
def fetch_questions_by_title(title):
    return list(db.collection("questions").where("title", "==", title).order_by("timestamp").stream())

# Session State の初期化
if "selected_title" not in st.session_state:
    st.session_state.selected_title = None
if "authenticated_questions" not in st.session_state:
    st.session_state.authenticated_questions = {}
if "pending_delete_msg_id" not in st.session_state:
    st.session_state.pending_delete_msg_id = None
if "pending_delete_title" not in st.session_state:
    st.session_state.pending_delete_title = None

# --- 投稿者認証のUI ---
def show_authentication_ui(title):
    st.info("この質問に対して投稿者認証を行いますか？")
    col1, col2 = st.columns(2)
    if col1.button("認証する", key=f"auth_yes_{title}"):
        st.session_state.authenticated_questions[title] = "pending"
        st.rerun()
    if col2.button("認証せずに閲覧", key=f"auth_no_{title}"):
        st.session_state.authenticated_questions[title] = False
        st.rerun()

# --- 認証チェック ---
def check_authentication(title):
    if title in st.session_state.authenticated_questions and st.session_state.authenticated_questions[title] != "pending":
        return st.session_state.authenticated_questions[title]
    if title not in st.session_state.authenticated_questions:
        show_authentication_ui(title)
        return None
    if st.session_state.authenticated_questions.get(title) == "pending":
        st.info("投稿者パスワードを入力してください。")
        auth_pw = st.text_input("投稿者パスワード", type="password", key=f"auth_pw_{title}")
        if st.button("認証", key=f"auth_btn_{title}"):
            docs = fetch_questions_by_title(title)
            poster_pw = None
            for doc in docs:
                data = doc.to_dict()
                if not data.get("question", "").startswith("[SYSTEM]"):
                    poster_pw = data.get("poster_password")
                    break
            if poster_pw is None:
                st.error("認証情報が見つかりません。")
                return False
            if auth_pw == poster_pw:
                st.success("認証に成功しました！")
                st.session_state.authenticated_questions[title] = True
                st.rerun()
                return True
            else:
                st.error("パスワードが違います。")
                return False
        return None

# --- 質問タイトル一覧 ---
def show_title_list():
    st.title("📖 質問フォーラム")
    st.subheader("質問一覧")

    if st.button("＋ 新規質問を投稿"):
        st.session_state.selected_title = "__new_question__"
        st.rerun()

    keyword = st.text_input("キーワード検索")

    docs = fetch_all_questions()
    deleted_titles = set()
    for doc in docs:
        data = doc.to_dict()
        if data.get("question", "").startswith("[SYSTEM]投稿者はこの質問フォームを削除しました"):
            deleted_titles.add(data.get("title"))

    title_info = {}
    for doc in docs:
        data = doc.to_dict()
        title = data.get("title")
        if title in title_info:
            continue
        if not data.get("question", "").startswith("[SYSTEM]"):
            poster = data.get("poster", "不明")
            title_info[title] = poster

    distinct_titles = {t: poster for t, poster in title_info.items() if t not in deleted_titles}
    if keyword:
        distinct_titles = {t: poster for t, poster in distinct_titles.items() if keyword.lower() in t.lower() or keyword.lower() in poster.lower()}

    if not distinct_titles:
        st.write("現在、質問はありません。")
    else:
        for idx, (title, poster) in enumerate(distinct_titles.items()):
            cols = st.columns([4, 1])
            if cols[0].button(f"{title} (投稿者: {poster})", key=f"title_button_{idx}"):
                st.session_state.selected_title = title
                st.rerun()
            if cols[1].button("🗑", key=f"title_del_{idx}"):
                auth = check_authentication(title)
                if auth is True:
                    st.session_state.pending_delete_title = title
                    st.rerun()

    if st.session_state.pending_delete_title:
        title = st.session_state.pending_delete_title
        st.warning(f"本当にこのタイトルを削除しますか？")
        col1, col2 = st.columns(2)
        if col1.button("はい"):
            time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
            db.collection("questions").add({
                "title": title,
                "question": "[SYSTEM]投稿者はこの質問フォームを削除しました",
                "timestamp": time_str,
                "deleted": 0,
                "image": None
            })
            st.success("タイトルを削除しました。")
            st.session_state.pending_delete_title = None
            st.cache_resource.clear()
            st.rerun()
        if col2.button("キャンセル"):
            st.session_state.pending_delete_title = None
            st.rerun()

    if st.button("更新"):
        st.cache_resource.clear()
        st.rerun()

# --- 新規質問投稿 ---
def create_new_question():
    st.title("📝 新規質問を投稿")
    title = st.text_input("質問タイトル")
    poster = st.text_input("投稿者名（空欄の場合「匿名」になります）") or "匿名"
    poster_password = st.text_input("投稿者パスワード（後で管理用）", type="password")

    if st.button("投稿する"):
        if not title or not poster_password:
            st.warning("タイトルとパスワードを入力してください。")
            return
        time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
        db.collection("questions").add({
            "title": title,
            "question": "この質問に関する情報を記入してください。",
            "poster": poster,
            "poster_password": poster_password,
            "timestamp": time_str,
            "deleted": 0
        })
        st.success("質問を投稿しました！")
        st.session_state.selected_title = None
        st.cache_resource.clear()
        st.rerun()
