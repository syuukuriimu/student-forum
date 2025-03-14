import streamlit as st
import base64
from datetime import datetime
from zoneinfo import ZoneInfo  # タイムゾーン設定用
import firebase_admin
from firebase_admin import credentials, firestore
import sys
import ast

# experimental_rerun が存在しない場合の代替処理
if not hasattr(st, "experimental_rerun"):
    st.experimental_rerun = lambda: sys.exit()

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

# キャッシュを用いた Firestore アクセス（TTL 10秒）
@st.cache_resource(ttl=10)
def fetch_all_questions():
    return list(db.collection("questions").order_by("timestamp", direction=firestore.Query.DESCENDING).stream())

@st.cache_resource(ttl=10)
def fetch_questions_by_title(title):
    return list(db.collection("questions").where("title", "==", title).order_by("timestamp").stream())

# Session State の初期化
if "selected_title" not in st.session_state:
    st.session_state.selected_title = None
if "pending_delete_msg_id" not in st.session_state:
    st.session_state.pending_delete_msg_id = None
if "pending_delete_title" not in st.session_state:
    st.session_state.pending_delete_title = None
if "deleted_titles_student" not in st.session_state:
    st.session_state.deleted_titles_student = []

def show_title_list():
    st.title("📖 質問フォーラム")
    st.subheader("質問一覧")

    if st.button("＋ 新規質問を投稿"):
        st.session_state.selected_title = "__new_question__"
        st.experimental_rerun()

    # キーワード検索
    keyword = st.text_input("キーワード検索")

    docs = fetch_all_questions()

    # 生徒側削除のシステムメッセージで登録されたタイトルを除外
    deleted_system_titles = set()
    for doc in docs:
        data = doc.to_dict()
        if data.get("question", "").startswith("[SYSTEM]生徒はこの質問フォームを削除しました"):
            deleted_system_titles.add(data.get("title"))

    # 重複除去＆セッション内の削除済みタイトルも除外
    seen_titles = set()
    distinct_titles = []
    for doc in docs:
        data = doc.to_dict()
        title = data.get("title")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        if title in deleted_system_titles or title in st.session_state.deleted_titles_student:
            continue
        distinct_titles.append(title)

    # キーワードフィルタ（大文字小文字区別なし）
    if keyword:
        distinct_titles = [title for title in distinct_titles if keyword.lower() in title.lower()]

    if not distinct_titles:
        st.write("現在、質問はありません。")
    else:
        for idx, title in enumerate(distinct_titles):
            cols = st.columns([4, 1])
            if cols[0].button(title, key=f"title_button_{idx}"):
                st.session_state.selected_title = title
                st.experimental_rerun()
            if cols[1].button("🗑", key=f"title_del_{idx}"):
                st.session_state.pending_delete_title = title
                st.experimental_rerun()

    if st.button("更新"):
        st.cache_resource.clear()
        st.experimental_rerun()

def show_chat_thread():
    selected_title = st.session_state.selected_title
    if selected_title == "__new_question__":
        create_new_question()
        return

    st.title(f"質問詳細: {selected_title}")

    docs = fetch_questions_by_title(selected_title)

    records = [doc for doc in docs if not doc.to_dict().get("question", "").startswith("[SYSTEM]")]

    if not records:
        st.write("該当する質問が見つかりません。")
        return

    for doc in records:
        data = doc.to_dict()
        msg_id = doc.id
        msg_text = data.get("question", "")
        msg_img = data.get("image")
        msg_time = data.get("timestamp", "")

        if msg_text.startswith("[先生]"):
            sender = "先生"
            align = "left"
            bg_color = "#FFFFFF"
        else:
            sender = "自分"
            align = "right"
            bg_color = "#DCF8C6"

        st.markdown(
            f"""
            <div style="text-align: {align};">
              <div style="display: inline-block; background-color: {bg_color}; padding: 10px; border-radius: 10px; max-width: 35%;">
                <b>{sender}:</b> {msg_text}<br>
                <small>({msg_time})</small>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # 画像拡大機能
        if msg_img:
            img_data = base64.b64encode(msg_img).decode("utf-8")
            st.markdown(
                f'''
                <div style="text-align: {align};">
                  <a href="data:image/png;base64,{img_data}" target="_blank">
                    <img src="data:image/png;base64,{img_data}" style="max-width: 80%; height:auto;">
                  </a>
                </div>
                ''',
                unsafe_allow_html=True
            )

    st.write("---")

    with st.expander("返信する", expanded=True):
        with st.form("reply_form_student", clear_on_submit=True):
            reply_text = st.text_area("メッセージを入力")
            reply_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
            submitted = st.form_submit_button("送信")
            if submitted:
                time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
                img_data = reply_image.read() if reply_image else None
                db.collection("questions").add({
                    "title": selected_title,
                    "question": reply_text,
                    "image": img_data,
                    "timestamp": time_str
                })
                st.cache_resource.clear()
                st.experimental_rerun()  # 送信後にページを自動更新

    if st.button("戻る"):
        st.session_state.selected_title = None
        st.experimental_rerun()

def create_new_question():
    st.title("新規質問を投稿")
    # ここは変更なし

if st.session_state.selected_title is None:
    show_title_list()
else:
    show_chat_thread()
