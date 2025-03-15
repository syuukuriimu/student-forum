import streamlit as st
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
import firebase_admin
from firebase_admin import credentials, firestore
import ast

# ===============================
# セッションステートの初期化（教師用）
# ===============================
for key in ["authenticated", "is_authenticated", "selected_title", "pending_delete_msg_id", "pending_delete_title", "deleted_titles_teacher"]:
    if key not in st.session_state:
        if key in ["authenticated", "is_authenticated"]:
            st.session_state[key] = False
        elif key == "selected_title":
            st.session_state[key] = None
        else:
            st.session_state[key] = [] if "deleted_titles" in key else None

# ===============================
# ① 教師専用ログイン（認証機能）
# ===============================
if not st.session_state.authenticated:
    st.title("教師ログイン")
    password = st.text_input("パスワードを入力", type="password")
    if st.button("ログイン", key="teacher_login"):
        if password == st.secrets["teacher"]["password"]:
            st.session_state.authenticated = True
            st.session_state.is_authenticated = True
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop()

# ===============================
# ② Firestore 初期化
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
# ③ キャッシュを用いた Firestore アクセス（TTL 10秒）
# ===============================
@st.cache_resource(ttl=10)
def fetch_all_questions():
    return list(db.collection("questions")
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .stream())

@st.cache_resource(ttl=10)
def fetch_questions_by_title(title):
    return list(db.collection("questions")
                .where("title", "==", title)
                .order_by("timestamp")
                .stream())

# ===============================
# 質問一覧の表示（教師用）
# ===============================
def show_title_list():
    st.title("📖 質問フォーラム（教師用）")
    st.subheader("質問一覧")
    
    # キーワード検索（タイトル・投稿者名対象、スペース区切り）
    keyword_input = st.text_input("キーワード検索")
    keywords = [w.strip().lower() for w in keyword_input.split() if w.strip()] if keyword_input else []
    
    docs = fetch_all_questions()
    
    # 教師側削除システムメッセージのあるタイトルを抽出
    teacher_deleted_titles = { doc.to_dict().get("title")
                              for doc in docs
                              if doc.to_dict().get("question", "").startswith("[SYSTEM]先生は質問フォームを削除しました") }
    
    # 新規質問投稿時のオリジナル情報を保持するため、各タイトルについて
    # 最も古い (最小) timestamp をオリジナル情報、最新のtimestampを更新日時(update)として保持
    title_info = {}
    for doc in docs:
        data = doc.to_dict()
        # システムメッセージは除外
        if data.get("question", "").startswith("[SYSTEM]"):
            continue
        title = data.get("title")
        poster = data.get("poster") or "匿名"
        auth_key = data.get("auth_key", "")
        timestamp = data.get("timestamp", "")
        if title in title_info:
            # オリジナル情報は、最小のtimestamp
            if timestamp < title_info[title]["orig_timestamp"]:
                title_info[title]["orig_timestamp"] = timestamp
                title_info[title]["poster"] = poster
                title_info[title]["auth_key"] = auth_key
            # 更新日時は最大のtimestamp
            if timestamp > title_info[title]["update"]:
                title_info[title]["update"] = timestamp
        else:
            title_info[title] = {"poster": poster, "auth_key": auth_key, "orig_timestamp": timestamp, "update": timestamp}
    
    distinct_titles = []
    for title, info in title_info.items():
        if title in teacher_deleted_titles or title in st.session_state.deleted_titles_teacher:
            continue
        distinct_titles.append({
            "title": title,
            "poster": info["poster"],
            "auth_key": info["auth_key"],
            "update": info["update"]
        })
    
    # 検索フィルタ：タイトルまたは投稿者名に全キーワードが含まれるか
    if keywords:
        def match(item):
            text = (item["title"] + " " + item["poster"]).lower()
            return all(kw in text for kw in keywords)
        distinct_titles = [item for item in distinct_titles if match(item)]
    
    # ソート：更新日時降順
    distinct_titles.sort(key=lambda x: x["update"], reverse=True)
    
    if not distinct_titles:
        st.write("現在、質問はありません。")
    else:
        # カラム比率 [8,2]：タイトル（認証コードも確実に表示）と削除ボタン
        for idx, item in enumerate(distinct_titles):
            title = item["title"]
            poster = item["poster"]
            auth_code = item["auth_key"]
            update_time = item["update"]
            cols = st.columns([8, 2])
            label = f"{title}\n(投稿者: {poster}, 認証コード: {auth_code})\n最終更新: {update_time}"
            if cols[0].button(label, key=f"teacher_title_{idx}"):
                st.session_state.selected_title = title
                st.rerun()
            if cols[1].button("🗑", key=f"teacher_del_{idx}"):
                st.session_state.pending_delete_title = title
                st.rerun()
    
    # タイトル削除確認（認証キー確認は不要、単純確認のみ）
    if st.session_state.pending_delete_title:
        title = st.session_state.pending_delete_title
        st.warning(f"本当に「{title}」を削除してよろしいですか？")
        cols = st.columns(2)
        if cols[0].button("はい", key="teacher_del_confirm"):
            # オリジナルの投稿者と認証コードをそのまま保持
            docs = fetch_questions_by_title(title)
            if docs:
                data0 = docs[0].to_dict()
                stored_auth_key = data0.get("auth_key", "")
                poster_name = data0.get("poster") or "匿名"
            else:
                stored_auth_key = ""
                poster_name = "匿名"
            st.session_state.pending_delete_title = None
            st.session_state.deleted_titles_teacher.append(title)
            time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
            db.collection("questions").add({
                "title": title,
                "question": "[SYSTEM]先生は質問フォームを削除しました",
                "timestamp": time_str,
                "deleted": 0,
                "image": None,
                "poster": poster_name,
                "auth_key": stored_auth_key
            })
            st.success("タイトルを削除しました。")
            # 両側で削除されていた場合は完全削除
            student_msgs = list(
                db.collection("questions")
                .where("title", "==", title)
                .where("question", "==", "[SYSTEM]生徒はこの質問フォームを削除しました")
                .stream()
            )
            if student_msgs:
                docs_to_delete = list(db.collection("questions").where("title", "==", title).stream())
                for d in docs_to_delete:
                    d.reference.delete()
            st.cache_resource.clear()
            st.rerun()
        if cols[1].button("キャンセル", key="teacher_del_cancel"):
            st.session_state.pending_delete_title = None
            st.rerun()
    
    if st.button("更新", key="teacher_title_update"):
        st.cache_resource.clear()
        st.rerun()

# ===============================
# 質問詳細（チャットスレッド）の表示（教師用）
# ===============================
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
        poster = data.get("poster") or "匿名"
        deleted = data.get("deleted", 0)
        try:
            formatted_time = datetime.strptime(msg_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M")
        except Exception:
            formatted_time = msg_time
        
        if deleted:
            st.markdown("<div style='color: red;'>【投稿が削除されました】</div>", unsafe_allow_html=True)
            continue
        
        # 修正：教師の投稿は右側・背景緑、生徒の投稿は左側・背景白
        if msg_text.startswith("[先生]"):
            sender = "先生"
            msg_display = msg_text[len("[先生]"):].strip()
            align = "right"
            bg_color = "#DCF8C6"
        else:
            sender = poster
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
            if st.button("🗑", key=f"teacher_chat_del_{doc.id}"):
                st.session_state.pending_delete_msg_id = doc.id
                st.rerun()
            if st.session_state.get("pending_delete_msg_id") == doc.id:
                st.warning("本当にこの投稿を削除しますか？")
                confirm_col1, confirm_col2 = st.columns(2)
                if confirm_col1.button("はい", key=f"teacher_confirm_delete_{doc.id}"):
                    d_ref = db.collection("questions").document(doc.id)
                    d_ref.update({"deleted": 1})
                    st.session_state.pending_delete_msg_id = None
                    st.cache_resource.clear()
                    st.rerun()
                if confirm_col2.button("キャンセル", key=f"teacher_cancel_delete_{doc.id}"):
                    st.session_state.pending_delete_msg_id = None
                    st.rerun()

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
    if st.button("更新", key="teacher_chat_update"):
        st.cache_resource.clear()
        st.rerun()
    
    if st.session_state.is_authenticated:
        with st.expander("返信する", expanded=False):
            with st.form("teacher_reply_form", clear_on_submit=True):
                reply_text = st.text_area("メッセージを入力（自動的に [先生] が付与されます）")
                reply_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
                submitted = st.form_submit_button("送信")
                if submitted:
                    time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
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
                    st.rerun()
    if st.button("戻る", key="teacher_chat_back"):
        st.session_state.selected_title = None
        st.rerun()

def create_new_question():
    st.title("新規質問を投稿")
    with st.form("teacher_new_question_form", clear_on_submit=False):
        new_title = st.text_input("質問のタイトルを入力", key="teacher_new_title")
        new_text = st.text_area("質問内容を入力", key="teacher_new_text")
        new_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="teacher_new_image")
        poster_name = st.text_input("投稿者名 (空白の場合は匿名)", key="teacher_poster_name")
        auth_key = st.text_input("認証キーを設定 (必須入力, 10文字まで)", type="password", key="teacher_new_auth_key", max_chars=10)
        st.caption("認証キーは返信やタイトル削除等に必要です。")
        submitted = st.form_submit_button("投稿")
    if submitted:
        if not new_title or not new_text:
            st.error("タイトルと質問内容は必須です。")
        elif auth_key == "":
            st.error("認証キーは必須入力です。")
            try:
                st.session_state["teacher_new_auth_key"] = ""
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
                st.session_state["teacher_new_auth_key"] = ""
            except Exception:
                pass
            st.rerun()
    
    if st.button("戻る", key="teacher_new_back"):
        st.session_state.selected_title = None
        st.rerun()

# ===============================
# メイン表示の切り替え（教師用）
# ===============================
if st.session_state.selected_title is None:
    show_title_list()
else:
    show_chat_thread()
