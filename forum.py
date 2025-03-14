import streamlit as st
import base64
from datetime import datetime
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
    
    # 新規質問を投稿
    if st.button("＋ 新規質問を投稿"):
        st.session_state.selected_title = "__new_question__"
        # ここでは rerun せず、下のフローで自動的に画面が切り替わる
        return
    
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
    
    # キーワードフィルタ
    if keyword:
        distinct_titles = [title for title in distinct_titles if keyword.lower() in title.lower()]
    
    if not distinct_titles:
        st.write("現在、質問はありません。")
    else:
        for idx, title in enumerate(distinct_titles):
            cols = st.columns([4, 1])
            if cols[0].button(title, key=f"title_button_{idx}"):
                st.session_state.selected_title = title
                return
            if cols[1].button("🗑", key=f"title_del_{idx}"):
                st.session_state.pending_delete_title = title
                return
    
    # 削除確認
    if st.session_state.pending_delete_title:
        title = st.session_state.pending_delete_title
        st.warning(f"本当にこのタイトルを削除しますか？")
        confirm_col1, confirm_col2 = st.columns(2)
        if confirm_col1.button("はい"):
            st.session_state.pending_delete_title = None
            st.session_state.deleted_titles_student.append(title)
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.collection("questions").add({
                "title": title,
                "question": "[SYSTEM]生徒はこの質問フォームを削除しました",
                "timestamp": time_str,
                "deleted": 0,
                "image": None
            })
            st.success("タイトルを削除しました。")
            # 先生側も削除済みなら全件削除
            teacher_msgs = list(db.collection("questions")
                                .where("title", "==", title)
                                .where("question", "==", "[SYSTEM]先生は質問フォームを削除しました")
                                .stream())
            if len(teacher_msgs) > 0:
                docs_to_delete = list(db.collection("questions").where("title", "==", title).stream())
                for d in docs_to_delete:
                    d.reference.delete()
            st.cache_resource.clear()
        if confirm_col2.button("キャンセル"):
            st.session_state.pending_delete_title = None

    if st.button("更新"):
        st.cache_resource.clear()

def show_chat_thread():
    selected_title = st.session_state.selected_title
    if selected_title == "__new_question__":
        create_new_question()
        return
    
    st.title(f"質問詳細: {selected_title}")
    
    docs = fetch_questions_by_title(selected_title)
    
    # システムメッセージ
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
        
        # メッセージ表示
        if msg_text.startswith("[先生]"):
            sender = "先生"
            is_self = False
            msg_display = msg_text[len("[先生]"):].strip()
            align = "left"
            bg_color = "#FFFFFF"
        else:
            sender = "自分"
            is_self = True
            msg_display = msg_text
            align = "right"
            bg_color = "#DCF8C6"
        
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
                f"""
                <div style="text-align: {align};">
                  <div style="display: inline-block; padding: 5px; border-radius: 5px;">
                    <img src="data:image/png;base64,{img_data}" style="max-width: 80%; height:auto;">
                  </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        # 自分の投稿のみ削除ボタン
        if is_self:
            if st.button("🗑", key=f"del_{msg_id}"):
                st.session_state.pending_delete_msg_id = msg_id
    
    # 投稿削除確認
    if st.session_state.pending_delete_msg_id:
        st.warning("本当にこの投稿を削除しますか？")
        confirm_col1, confirm_col2 = st.columns(2)
        if confirm_col1.button("はい", key="confirm_delete"):
            doc_id = st.session_state.pending_delete_msg_id
            st.session_state.pending_delete_msg_id = None
            doc_ref = db.collection("questions").document(doc_id)
            doc_ref.update({"deleted": 1})
            st.cache_resource.clear()
        if confirm_col2.button("キャンセル", key="cancel_delete"):
            st.session_state.pending_delete_msg_id = None

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
    if st.button("更新"):
        st.cache_resource.clear()
    
    # 返信フォーム（連続返信を可能にするため、rerunを削除）
    with st.expander("返信する", expanded=True):
        with st.form("reply_form_student", clear_on_submit=True):
            reply_text = st.text_area("メッセージを入力")
            reply_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
            submitted = st.form_submit_button("送信")
            if submitted:
                time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                img_data = reply_image.read() if reply_image else None
                db.collection("questions").add({
                    "title": selected_title,
                    "question": reply_text,
                    "image": img_data,
                    "timestamp": time_str,
                    "deleted": 0
                })
                st.cache_resource.clear()
                st.success("返信を送信しました！")
                # ここで experimental_rerun を呼ばず、フォームを表示し続ける

    if st.button("戻る"):
        st.session_state.selected_title = None
        # ここも rerun は不要

def create_new_question():
    st.title("新規質問を投稿")
    with st.form("new_question_form", clear_on_submit=True):
        new_title = st.text_input("質問のタイトルを入力")
        new_text = st.text_area("質問内容を入力")
        new_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
        submitted = st.form_submit_button("投稿")
        if submitted and new_title and new_text:
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            img_data = new_image.read() if new_image else None
            db.collection("questions").add({
                "title": new_title,
                "question": new_text,
                "image": img_data,
                "timestamp": time_str,
                "deleted": 0
            })
            st.cache_resource.clear()
            st.success("質問を投稿しました！")
            st.session_state.selected_title = new_title
            # rerun は呼ばず、下のフローで再表示
    
    if st.button("戻る"):
        st.session_state.selected_title = None
        # rerun は呼ばない

# メイン表示の切り替え
if st.session_state.selected_title is None:
    show_title_list()
else:
    show_chat_thread()
