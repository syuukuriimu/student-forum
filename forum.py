import streamlit as st
import base64
from datetime import datetime
from zoneinfo import ZoneInfo  # タイムゾーン設定用
import firebase_admin
from firebase_admin import credentials, firestore
import ast

# ===============================
# Firestore 初期化
# ===============================
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

# ===============================
# キャッシュを用いた Firestore アクセス（TTL 10秒）
# ===============================
@st.cache_resource(ttl=10)
def fetch_all_questions():
    return list(
        db.collection("questions")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .stream()
    )

@st.cache_resource(ttl=10)
def fetch_questions_by_title(title):
    return list(
        db.collection("questions")
        .where("title", "==", title)
        .order_by("timestamp")
        .stream()
    )

# ===============================
# Session State の初期化
# ===============================
if "selected_title" not in st.session_state:
    st.session_state.selected_title = None
if "pending_delete_msg_id" not in st.session_state:
    st.session_state.pending_delete_msg_id = None
if "pending_delete_title" not in st.session_state:
    st.session_state.pending_delete_title = None
if "deleted_titles_student" not in st.session_state:
    st.session_state.deleted_titles_student = []
if "pending_auth_title" not in st.session_state:
    st.session_state.pending_auth_title = None
if "is_authenticated" not in st.session_state:
    st.session_state.is_authenticated = False
if "poster" not in st.session_state:
    st.session_state.poster = None

##############################
# 新規質問投稿フォーム（生徒側）
# 初めは閉じた状態（expander を collapsed に）
##############################
def show_new_question_form():
    with st.expander("新規質問を投稿する（クリックして開く）", expanded=False):
        st.subheader("新規質問を投稿")
        with st.form("new_question_form", clear_on_submit=False):
            new_title = st.text_input("質問のタイトルを入力", key="new_title")
            new_text = st.text_area("質問内容を入力", key="new_text")
            new_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="new_image")
            poster_name = st.text_input("投稿者名 (空白の場合は匿名)", key="poster_name")
            # 認証キーは必須、10文字までに制限、説明文追加
            auth_key = st.text_input("認証キーを設定 (必須入力, 10文字まで)", type="password", key="new_auth_key", max_chars=10)
            st.caption("認証キーは返信やタイトル削除等に必要です。")
            submitted = st.form_submit_button("投稿")
        if submitted:
            if not new_title or not new_text:
                st.error("タイトルと質問内容は必須です。")
            elif auth_key == "":
                st.error("認証キーは必須入力です。")
                try:
                    st.session_state["new_auth_key"] = ""
                except Exception:
                    pass
            else:
                if not poster_name:
                    poster_name = "匿名"
                time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
                img_data = new_image.read() if new_image else None
                db.collection("questions").add({
                    "title": new_title,
                    "question": new_text,
                    "image": img_data,
                    "timestamp": time_str,
                    "deleted": 0,
                    "poster": poster_name,
                    "auth_key": auth_key
                })
                st.cache_resource.clear()
                st.success("質問を投稿しました！")
                st.session_state.selected_title = new_title
                st.session_state.is_authenticated = True
                st.session_state.poster = poster_name
                try:
                    st.session_state["new_auth_key"] = ""
                except Exception:
                    pass
                st.experimental_rerun()

##############################
# 質問一覧の表示（生徒側）
##############################
def show_title_list():
    st.title("📖 質問フォーラム")
    # 新規投稿フォームをページ上部に表示
    show_new_question_form()
    
    st.subheader("質問一覧")
    
    # 検索：入力文字列をスペースで分割して、タイトルおよび投稿者名にすべての単語が含まれているか
    keyword_input = st.text_input("キーワード検索")
    keywords = [w.strip().lower() for w in keyword_input.split() if w.strip()] if keyword_input else []
    
    docs = fetch_all_questions()
    
    # 生徒側削除システムメッセージ（"[SYSTEM]生徒はこの質問フォームを削除しました"）のタイトルを除外
    deleted_system_titles = set()
    for doc in docs:
        data = doc.to_dict()
        if data.get("question", "").startswith("[SYSTEM]生徒はこの質問フォームを削除しました"):
            deleted_system_titles.add(data.get("title"))
    
    # ユーザー投稿情報（システムメッセージ以外）の取得
    title_info = {}
    for doc in docs:
        data = doc.to_dict()
        if data.get("question", "").startswith("[SYSTEM]"):
            continue
        title = data.get("title")
        poster = data.get("poster", "匿名")
        timestamp = data.get("timestamp", "")
        auth_key = data.get("auth_key", "")
        if title in title_info:
            if timestamp > title_info[title]["update"]:
                title_info[title]["update"] = timestamp
        else:
            title_info[title] = {"poster": poster, "update": timestamp, "auth_key": auth_key}
    
    distinct_titles = []
    for title, info in title_info.items():
        if title in deleted_system_titles or title in st.session_state.deleted_titles_student:
            continue
        distinct_titles.append({
            "title": title,
            "poster": info["poster"],
            "auth_key": info["auth_key"],
            "update": info["update"]
        })
    
    # 検索フィルタ：タイトル or 投稿者名にすべてのキーワードが含まれているか
    if keywords:
        def match(item):
            text = (item["title"] + " " + item["poster"]).lower()
            return all(kw in text for kw in keywords)
        distinct_titles = [item for item in distinct_titles if match(item)]
    
    # ソート：最終更新日時の降順
    distinct_titles.sort(key=lambda x: x["update"], reverse=True)
    
    if not distinct_titles:
        st.write("現在、質問はありません。")
    else:
        # カラム比率 [8,2]：タイトルと削除ボタンを同一行に配置（スマホ対応）
        for idx, item in enumerate(distinct_titles):
            title = item["title"]
            poster = item["poster"]
            update_time = item["update"]
            cols = st.columns([8,2])
            # 認証コードは表示しない（生徒側）
            label = f"{title}\n(投稿者: {poster})\n最終更新: {update_time}"
            if cols[0].button(label, key=f"title_button_{idx}"):
                st.session_state.pending_auth_title = title
                st.experimental_rerun()
            if cols[1].button("🗑", key=f"title_del_{idx}"):
                st.session_state.pending_delete_title = title
                st.experimental_rerun()
    
    # タイトル削除確認（認証キー確認付き）
    if st.session_state.pending_delete_title:
        title = st.session_state.pending_delete_title
        st.warning("このタイトルを削除するには認証キーを入力してください。")
        with st.form("delete_title_form"):
            delete_auth_key = st.text_input("認証キー", type="password")
            delete_submit = st.form_submit_button("削除する")
        if delete_submit:
            docs = fetch_questions_by_title(title)
            if docs:
                stored_auth_key = docs[0].to_dict().get("auth_key", "")
                if delete_auth_key == stored_auth_key:
                    st.session_state.pending_delete_title = None
                    st.session_state.deleted_titles_student.append(title)
                    time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
                    poster_name = title_info.get(title, {}).get("poster", "匿名")
                    db.collection("questions").add({
                        "title": title,
                        "question": "[SYSTEM]生徒はこの質問フォームを削除しました",
                        "timestamp": time_str,
                        "deleted": 0,
                        "image": None,
                        "poster": poster_name,
                        "auth_key": title_info.get(title, {}).get("auth_key", "")
                    })
                    st.success("タイトルを削除しました。")
                    # 両側で削除された場合は、完全にDBから削除
                    teacher_msgs = list(
                        db.collection("questions")
                        .where("title", "==", title)
                        .where("question", "==", "[SYSTEM]先生は質問フォームを削除しました")
                        .stream()
                    )
                    if teacher_msgs:
                        docs_to_delete = list(db.collection("questions").where("title", "==", title).stream())
                        for d in docs_to_delete:
                            d.reference.delete()
                    st.cache_resource.clear()
                    st.experimental_rerun()
                else:
                    st.error("認証キーが正しくありません。")
        if st.button("キャンセル", key="del_confirm_no"):
            st.session_state.pending_delete_title = None
            st.experimental_rerun()
    
    if st.button("更新", key="title_update"):
        st.cache_resource.clear()
        st.experimental_rerun()

##############################
# 質問詳細（チャットスレッド）の表示（生徒側）
##############################
def show_chat_thread():
    selected_title = st.session_state.selected_title
    st.title(f"質問詳細: {selected_title}")
    
    docs = fetch_questions_by_title(selected_title)
    
    # システムメッセージの表示（赤字・中央寄せ）
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
        msg_text = data.get("question", "")
        msg_time = data.get("timestamp", "")
        poster = data.get("poster", "匿名")
        deleted = data.get("deleted", 0)
        try:
            formatted_time = datetime.strptime(msg_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M")
        except Exception:
            formatted_time = msg_time
        
        if deleted:
            st.markdown("<div style='color: red;'>【投稿が削除されました】</div>", unsafe_allow_html=True)
            continue
        
        # 修正：生徒側では、教師の投稿は左寄せ・背景白、生徒の投稿は右寄せ・背景緑
        if msg_text.startswith("[先生]"):
            sender = "先生"
            msg_display = msg_text[len("[先生]"):].strip()
            align = "left"
            bg_color = "#FFFFFF"
        else:
            sender = poster
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
        
        if "image" in data and data["image"]:
            img_data = base64.b64encode(data["image"]).decode("utf-8")
            st.markdown(
                f'''
                <div style="text-align: {align}; margin-bottom: 15px;">
                    <img src="data:image/png;base64,{img_data}" style="max-width: 80%; height:auto;">
                </div>
                ''',
                unsafe_allow_html=True
            )
        st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
        
        if st.session_state.is_authenticated and msg_text and not msg_text.startswith("[先生]"):
            if st.button("🗑", key=f"del_{doc.id}"):
                st.session_state.pending_delete_msg_id = doc.id
                st.experimental_rerun()
            if st.session_state.pending_delete_msg_id == doc.id:
                st.warning("本当にこの投稿を削除しますか？")
                confirm_col1, confirm_col2 = st.columns(2)
                if confirm_col1.button("はい", key=f"confirm_delete_{doc.id}"):
                    d_ref = db.collection("questions").document(doc.id)
                    d_ref.update({"deleted": 1})
                    st.session_state.pending_delete_msg_id = None
                    st.cache_resource.clear()
                    st.experimental_rerun()
                if confirm_col2.button("キャンセル", key=f"cancel_delete_{doc.id}"):
                    st.session_state.pending_delete_msg_id = None
                    st.experimental_rerun()

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
    if st.button("更新", key="chat_update"):
        st.cache_resource.clear()
        st.experimental_rerun()
    
    if st.session_state.is_authenticated:
        with st.expander("返信する", expanded=False):
            with st.form("reply_form_student", clear_on_submit=True):
                reply_text = st.text_area("メッセージを入力", key="reply_text")
                reply_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="reply_image")
                submitted = st.form_submit_button("送信")
                if submitted:
                    if reply_text == "":
                        st.error("メッセージを入力してください。")
                    else:
                        time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
                        img_data = reply_image.read() if reply_image else None
                        db.collection("questions").add({
                            "title": selected_title,
                            "question": reply_text,
                            "image": img_data,
                            "timestamp": time_str,
                            "deleted": 0,
                            "poster": st.session_state.poster
                        })
                        st.cache_resource.clear()
                        st.success("返信を送信しました！")
                        st.experimental_rerun()
    else:
        st.info("認証されていないため、返信はできません。")
    
    if st.button("戻る", key="chat_back"):
        st.session_state.selected_title = None
        st.session_state.is_authenticated = False
        st.session_state.poster = None
        st.experimental_rerun()

def create_new_question():
    st.title("新規質問を投稿")
    with st.form("new_question_form", clear_on_submit=False):
        new_title = st.text_input("質問のタイトルを入力", key="new_title")
        new_text = st.text_area("質問内容を入力", key="new_text")
        new_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="new_image")
        poster_name = st.text_input("投稿者名 (空白の場合は匿名)", key="poster_name")
        auth_key = st.text_input("認証キーを設定 (必須入力, 10文字まで)", type="password", key="new_auth_key", max_chars=10)
        st.caption("認証キーは返信やタイトル削除等に必要です。")
        submitted = st.form_submit_button("投稿")
    if submitted:
        if not new_title or not new_text:
            st.error("タイトルと質問内容は必須です。")
        elif auth_key == "":
            st.error("認証キーは必須入力です。")
            try:
                st.session_state["new_auth_key"] = ""
            except Exception:
                pass
        else:
            if not poster_name:
                poster_name = "匿名"
            time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
            img_data = new_image.read() if new_image else None
            db.collection("questions").add({
                "title": new_title,
                "question": new_text,
                "image": img_data,
                "timestamp": time_str,
                "deleted": 0,
                "poster": poster_name,
                "auth_key": auth_key
            })
            st.cache_resource.clear()
            st.success("質問を投稿しました！")
            st.session_state.selected_title = new_title
            st.session_state.is_authenticated = True
            st.session_state.poster = poster_name
            try:
                st.session_state["new_auth_key"] = ""
            except Exception:
                pass
            st.experimental_rerun()
    
    if st.button("戻る", key="new_back"):
        st.session_state.selected_title = None
        st.experimental_rerun()

# メイン表示の切り替え
if st.session_state.selected_title is None:
    show_title_list()
else:
    show_chat_thread()
