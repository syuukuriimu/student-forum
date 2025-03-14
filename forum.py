import streamlit as st
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
import firebase_admin
from firebase_admin import credentials, firestore
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
if "auth_state" not in st.session_state:
    st.session_state.auth_state = None  # 認証状態を保存

# 新規質問投稿
def create_new_question():
    st.title("新規質問を投稿")

    author = st.text_input("投稿者名（匿名可）")
    auth_key = st.text_input("認証キー（このキーで投稿を管理）", type="password")
    title = st.text_input("質問タイトル")
    question = st.text_area("質問内容")

    if st.button("投稿"):
        if not title or not question or not auth_key:
            st.error("タイトル、質問内容、認証キーは必須です。")
            return
        
        timestamp = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")

        # Firestore に保存
        db.collection("questions").add({
            "author": author if author else "匿名",
            "auth_key": auth_key,
            "title": title,
            "question": question,
            "timestamp": timestamp,
            "deleted": 0,
            "image": None
        })

        st.success("質問を投稿しました。")
        st.session_state.selected_title = title
        st.rerun()

# 質問一覧の表示
def show_title_list():
    st.title("📖 質問フォーラム")
    st.subheader("質問一覧")
    
    if st.button("＋ 新規質問を投稿"):
        st.session_state.selected_title = "__new_question__"
        st.rerun()
    
    keyword = st.text_input("キーワード検索")
    docs = fetch_all_questions()
    
    # 重複除去
    seen_titles = set()
    distinct_titles = [doc.to_dict()["title"] for doc in docs if doc.to_dict()["title"] not in seen_titles and not seen_titles.add(doc.to_dict()["title"])]

    # キーワード検索
    if keyword:
        distinct_titles = [title for title in distinct_titles if keyword.lower() in title.lower()]

    if not distinct_titles:
        st.write("現在、質問はありません。")
    else:
        for idx, title in enumerate(distinct_titles):
            cols = st.columns([4, 1])
            if cols[0].button(title, key=f"title_button_{idx}"):
                if st.session_state.auth_state is None:
                    auth_key = st.text_input("認証キーを入力", type="password")
                    if auth_key:
                        docs_with_title = fetch_questions_by_title(title)
                        stored_auth_key = docs_with_title[0].to_dict().get("auth_key", "")
                        if stored_auth_key == auth_key:
                            st.session_state.auth_state = True
                            st.session_state.selected_title = title
                            st.rerun()
                        else:
                            st.error("認証キーが一致しません。")
                else:
                    st.session_state.selected_title = title
                    st.rerun()

    if st.button("更新"):
        st.cache_resource.clear()
        st.rerun()

# 質問詳細ページ（チャット）
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
        msg_text = data.get("question", "")
        msg_img = data.get("image")
        msg_time = data.get("timestamp", "")
        deleted = data.get("deleted", 0)

        if deleted:
            st.markdown("<div style='color: red;'>【投稿が削除されました】</div>", unsafe_allow_html=True)
            continue

        sender = "自分" if "[先生]" not in msg_text else "先生"
        msg_display = msg_text.replace("[先生]", "").strip()
        align, bg_color = ("right", "#DCF8C6") if sender == "自分" else ("left", "#FFFFFF")

        st.markdown(
            f"""
            <div style="text-align: {align};">
              <div style="display: inline-block; background-color: {bg_color}; padding: 10px; border-radius: 10px; max-width: 35%;">
                <b>{sender}:</b> {msg_display}<br>
                <small>({msg_time})</small>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if msg_img:
            img_data = base64.b64encode(msg_img).decode("utf-8")
            st.markdown(
                f'''
                <div style="text-align: {align}; margin-bottom: 15px;">
                    <img src="data:image/png;base64,{img_data}" style="max-width: 80%; height:auto;">
                </div>
                ''',
                unsafe_allow_html=True
            )

    st.markdown("<div id='latest_message'></div>", unsafe_allow_html=True)

    if st.button("更新"):
        st.cache_resource.clear()
        st.rerun()

    with st.expander("返信する", expanded=False):
        with st.form("reply_form_student", clear_on_submit=True):
            reply_text = st.text_area("メッセージを入力")
            reply_image = st.file_uploader("画像を添付", type=["png", "jpg", "jpeg"])
            submitted = st.form_submit_button("送信")

            if submitted and reply_text:
                timestamp = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
                image_data = reply_image.read() if reply_image else None
                db.collection("questions").add({
                    "title": selected_title,
                    "question": reply_text,
                    "timestamp": timestamp,
                    "deleted": 0,
                    "image": image_data
                })
                st.success("メッセージを送信しました。")
                st.rerun()

# メイン処理
if st.session_state.selected_title:
    show_chat_thread()
else:
    show_title_list()
