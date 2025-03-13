import streamlit as st
import base64
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import sys

# experimental_rerun が存在しない場合の代替処理（今回は明示的な呼び出しを削除）
if not hasattr(st, "experimental_rerun"):
    st.experimental_rerun = lambda: sys.exit()

# Firestore 初期化
if not firebase_admin._apps:
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
if "deleted_titles_teacher" not in st.session_state:
    st.session_state.deleted_titles_teacher = []

def show_title_list():
    st.title("📖 質問フォーラム（教師用）")
    st.subheader("質問一覧")
    
    # Firestore から全メッセージを timestamp 降順で取得（キャッシュ関数使用）
    docs = fetch_all_questions()
    
    # 「先生側削除」のシステムメッセージで登録されたタイトルを除外
    teacher_deleted_titles = set()
    for doc in docs:
        data = doc.to_dict()
        if data.get("question", "").startswith("[SYSTEM]先生は質問フォームを削除しました"):
            teacher_deleted_titles.add(data.get("title"))
    
    # 重複除去＆教師側で削除済みのタイトルは除外（生徒側削除は表示する）
    seen_titles = set()
    distinct_titles = []
    for doc in docs:
        data = doc.to_dict()
        title = data.get("title")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        if title in teacher_deleted_titles or title in st.session_state.deleted_titles_teacher:
            continue
        distinct_titles.append(title)
    
    if not distinct_titles:
        st.write("現在、質問はありません。")
    else:
        for idx, title in enumerate(distinct_titles):
            cols = st.columns([4, 1])
            if cols[0].button(title, key=f"title_button_{idx}"):
                st.session_state.selected_title = title
            if cols[1].button("🗑", key=f"title_del_{idx}"):
                st.session_state.pending_delete_title = title
            if st.session_state.get("pending_delete_title") == title:
                st.warning(f"本当にこのタイトルを削除しますか？")
                confirm_col1, confirm_col2 = st.columns(2)
                if confirm_col1.button("はい", key=f"confirm_delete_{idx}"):
                    st.session_state.pending_delete_title = None
                    st.session_state.deleted_titles_teacher.append(title)
                    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    # 教師側削除システムメッセージを追加
                    db.collection("questions").add({
                        "title": title,
                        "question": "[SYSTEM]先生は質問フォームを削除しました",
                        "timestamp": time_str,
                        "deleted": 0,
                        "image": None
                    })
                    st.success("タイトルを削除しました。")
                    # もし既に生徒側削除システムメッセージが存在すれば、全件削除
                    student_msgs = list(db.collection("questions")
                                        .where("title", "==", title)
                                        .where("question", "==", "[SYSTEM]生徒はこの質問フォームを削除しました")
                                        .stream())
                    if len(student_msgs) > 0:
                        docs_to_delete = list(db.collection("questions").where("title", "==", title).stream())
                        for d in docs_to_delete:
                            d.reference.delete()
                    st.session_state.selected_title = None
                if confirm_col2.button("キャンセル", key=f"cancel_delete_{idx}"):
                    st.session_state.pending_delete_title = None
    
    if st.button("更新"):
        st.cache_resource.clear()

def show_chat_thread():
    selected_title = st.session_state.selected_title
    if selected_title is None:
        st.write("タイトルが選択されていません。")
        return
    
    st.title(f"質問詳細: {selected_title}")
    
    # 選択されたタイトルのメッセージを timestamp 昇順で取得（キャッシュ関数使用）
    docs = fetch_questions_by_title(selected_title)
    
    # システムメッセージを中央寄せの赤色テキストで表示
    sys_msgs = [doc.to_dict() for doc in docs if doc.to_dict().get("question", "").startswith("[SYSTEM]")]
    if sys_msgs:
        for sys_msg in sys_msgs:
            text = sys_msg.get("question", "")[8:]
            st.markdown(f"<h3 style='color: red; text-align: center;'>{text}</h3>", unsafe_allow_html=True)
    
    records = [doc for doc in docs if not doc.to_dict().get("question", "").startswith("[SYSTEM]")]
    
    if records and all(doc.to_dict().get("deleted", 0) == 2 for doc in records):
        st.markdown("<h3 style='color: red;'>先生はこのフォーラムを削除しました</h3>", unsafe_allow_html=True)
    else:
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
            # 削除済みの場合の表示（forum.py と同様）
            if deleted:
                st.markdown("<div style='color: red;'>【投稿が削除されました】</div>", unsafe_allow_html=True)
                continue
            # 教師が投稿したメッセージは [先生] プレフィックスが付く
            if msg_text.startswith("[先生]"):
                sender = "先生"
                is_self = True
                msg_display = msg_text[len("[先生]"):].strip()
                align = "right"
                bg_color = "#DCF8C6"
            else:
                sender = "生徒"
                is_self = False
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
                    f"""
                    <div style="text-align: {align};">
                      <div style="display: inline-block; padding: 5px; border-radius: 5px;">
                        <img src="data:image/png;base64,{img_data}" style="max-width: 80%; height:auto;">
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            # 教師側は自身の投稿に対して削除ボタンを表示
            if is_self:
                if st.button("🗑", key=f"del_{msg_id}"):
                    st.session_state.pending_delete_msg_id = msg_id
                if st.session_state.get("pending_delete_msg_id") == msg_id:
                    st.warning("本当にこの投稿を削除しますか？")
                    confirm_col1, confirm_col2 = st.columns(2)
                    if confirm_col1.button("はい", key=f"confirm_del_{msg_id}"):
                        st.session_state.pending_delete_msg_id = None
                        doc.reference.update({"deleted": 2})
                    if confirm_col2.button("キャンセル", key=f"cancel_del_{msg_id}"):
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
    if st.button("更新", key="update_chat"):
        st.cache_resource.clear()
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
                st.success("返信を送信しました！")
    if st.button("戻る"):
        st.session_state.selected_title = None

# メイン表示の切り替え
if st.session_state.selected_title is None:
    show_title_list()
else:
    show_chat_thread()
