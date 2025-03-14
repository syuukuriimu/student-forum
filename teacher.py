import streamlit as st
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
import firebase_admin
from firebase_admin import credentials, firestore
import sys
import ast

# --- 認証機能（教師専用ログイン） ---
if "authenticated_teacher" not in st.session_state:
    st.session_state.authenticated_teacher = False

if not st.session_state.authenticated_teacher:
    st.title("教師ログイン")
    teacher_pw = st.text_input("パスワードを入力", type="password")
    if st.button("ログイン"):
        if teacher_pw == st.secrets["teacher"]["password"]:
            st.session_state.authenticated_teacher = True
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop()

# --- Firestore 初期化 ---
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

# --- キャッシュを用いた Firestore アクセス（TTL 10秒） ---
@st.cache_resource(ttl=10)
def fetch_all_questions():
    return list(db.collection("questions").order_by("timestamp", direction=firestore.Query.DESCENDING).stream())

@st.cache_resource(ttl=10)
def fetch_questions_by_title(title):
    return list(db.collection("questions").where("title", "==", title).order_by("timestamp").stream())

# --- Session State の初期化（教師用） ---
if "selected_title" not in st.session_state:
    st.session_state.selected_title = None
if "pending_delete_msg_id" not in st.session_state:
    st.session_state.pending_delete_msg_id = None
if "pending_delete_title" not in st.session_state:
    st.session_state.pending_delete_title = None
if "deleted_titles_teacher" not in st.session_state:
    st.session_state.deleted_titles_teacher = {}

# --- 質問一覧の表示 ---
def show_title_list():
    st.title("📖 質問フォーラム（教師用）")
    st.subheader("質問一覧")
    
    # 新規質問投稿は不可
    keyword = st.text_input("キーワード検索")
    docs = fetch_all_questions()
    
    # 学生側削除システムメッセージを除外
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
                # 削除は教師側認証のみで実施
                st.session_state.pending_delete_title = title
                st.rerun()
    
    if st.session_state.pending_delete_title:
        title = st.session_state.pending_delete_title
        st.warning(f"本当にこのタイトルを削除しますか？")
        col1, col2 = st.columns(2)
        if col1.button("はい"):
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.collection("questions").add({
                "title": title,
                "question": "[SYSTEM]先生は質問フォームを削除しました",
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

# --- 詳細フォーラム（チャットスレッド）の表示 ---
def show_chat_thread():
    selected_title = st.session_state.selected_title
    st.title(f"質問詳細: {selected_title}")
    docs = fetch_questions_by_title(selected_title)
    
    sys_msgs = [doc.to_dict() for doc in docs if doc.to_dict().get("question", "").startswith("[SYSTEM]")]
    if sys_msgs:
        for sys_msg in sys_msgs:
            text = sys_msg.get("question", "")[8:]
            st.markdown(f"<h3 style='color: red; text-align: center;'>{text}</h3>", unsafe_allow_html=True)
    
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
        deleted = data.get("deleted", 0)
        try:
            formatted_time = datetime.strptime(msg_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M")
        except Exception:
            formatted_time = msg_time
        if deleted:
            st.markdown("<div style='color: red;'>【投稿が削除されました】</div>", unsafe_allow_html=True)
            continue
        
        if msg_text.startswith("[先生]"):
            sender = "先生"
            is_own = True
            msg_display = msg_text[len("[先生]"):].strip()
            align = "right"
            bg_color = "#DCF8C6"
        else:
            sender = "生徒"
            is_own = False
            msg_display = msg_text
            align = "left"
            bg_color = "#FFFFFF"
        
        st.markdown(
            f"""
            <div style="text-align: {align};">
              <div style="display: inline-block; background-color: {bg_color}; padding: 10px; border-radius: 10px; max-width: 35%;">
                <b>{sender}:</b> {msg_display}<br>
                <small>({formatted_time})</small>
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
        st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
        
        # 教師側では個別削除は表示せず、タイトル削除で対応する
    st.markdown("<div id='latest_message'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <script>
        const el = document.getElementById('latest_message');
        if(el){
             el.scrollIntoView({behavior: 'smooth'});
        }
        </script>
        """,
        unsafe_allow_html=True
    )
    st.write("---")
    if st.button("更新", key="update_chat"):
        st.cache_resource.clear()
        st.rerun()
    
    with st.expander("返信する"):
        with st.form("reply_form_teacher", clear_on_submit=True):
            reply_text = st.text_area("メッセージを入力（自動的に [先生] が付与されます）")
            reply_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
            submitted = st.form_submit_button("送信")
            if submitted:
                time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                img_data = reply_image.read() if reply_image else None
                db.collection("questions").add({
                    "title": selected_title,
                    "question": "[先生] " + reply_text,
                    "image": img_data,
                    "timestamp": time_str,
                    "deleted": 0
                })
                st.cache_resource.clear()
                st.success("返信を送信しました！")
    if st.button("戻る", key="back_btn"):
        st.session_state.selected_title = None
        st.rerun()

# --- メイン表示の切り替え ---
if st.session_state.selected_title is None:
    show_title_list()
else:
    show_chat_thread()

