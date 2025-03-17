import streamlit as st
import base64
from datetime import datetime
from zoneinfo import ZoneInfo  # タイムゾーン設定用
import firebase_admin
from firebase_admin import credentials, firestore
import ast
import cv2
import numpy as np

# ---------- CSS 注入：新規質問投稿 Expander ヘッダー背景（黄緑） ----------
st.markdown(
    """
    <style>
    [data-baseweb="accordion"] > div[role="button"] {
        background-color: #CCFFCC !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------- 生徒ログイン ----------
if "student_authenticated" not in st.session_state:
    st.session_state.student_authenticated = False

if not st.session_state.student_authenticated:
    st.title("生徒ログイン")
    password = st.text_input("パスワードを入力", type="password")
    if st.button("ログイン", key="student_login"):
        if password == st.secrets["student"]["password"]:
            st.session_state.student_authenticated = True
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop()

# ---------- 画像圧縮処理 ----------
def process_image(image_file, max_size=1000000, max_width=800, initial_quality=95):
    try:
        image_file.seek(0)
        file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    except Exception:
        st.error("画像の読み込みに失敗しました。")
        return None
    if img is None:
        st.error("画像のデコードに失敗しました。")
        return None
    height, width, _ = img.shape
    if width > max_width:
        ratio = max_width / width
        new_width = max_width
        new_height = int(height * ratio)
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
    quality = initial_quality
    while quality >= 10:
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        result, encimg = cv2.imencode('.jpg', img, encode_param)
        if not result:
            st.error("画像の圧縮に失敗しました。")
            return None
        size = encimg.nbytes
        if size <= max_size:
            return encimg.tobytes()
        quality -= 5
    st.error("画像の圧縮に失敗しました。")
    return None

# ---------- Firestore 初期化 ----------
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

# ---------- キャッシュ付き Firestore アクセス ----------
@st.cache_resource(ttl=10)
def fetch_all_questions():
    return list(db.collection("questions").order_by("timestamp", direction=firestore.Query.DESCENDING).stream())
@st.cache_resource(ttl=10)
def fetch_questions_by_title(title):
    return list(db.collection("questions").where("title", "==", title).order_by("timestamp").stream())

# ---------- Session State 初期化 ----------
if "selected_title" not in st.session_state:
    st.session_state.selected_title = None
if "pending_auth_title" not in st.session_state:
    st.session_state.pending_auth_title = None
if "pending_delete_title" not in st.session_state:
    st.session_state.pending_delete_title = None
if "deleted_titles_student" not in st.session_state:
    st.session_state.deleted_titles_student = []
if "is_authenticated" not in st.session_state:
    st.session_state.is_authenticated = False
if "poster" not in st.session_state:
    st.session_state.poster = None
if "pending_delete_msg_id" not in st.session_state:
    st.session_state.pending_delete_msg_id = None

#####################################
# 新規質問投稿フォーム
#####################################
def show_new_question_form():
    st.expander("新規質問を投稿する（クリックして開く）", expanded=False)
    with st.container():
        st.subheader("新規質問を投稿")
        with st.form("new_question_form", clear_on_submit=False):
            new_title = st.text_input("質問のタイトルを入力", key="new_title")
            new_text = st.text_area("質問内容を入力", key="new_text")
            new_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="new_image")
            poster_name = st.text_input("投稿者名 (空白の場合は匿名)", key="poster_name")
            auth_key = st.text_input("認証キーを設定 (必須入力, 10文字まで)", type="password", key="new_auth_key", max_chars=10)
            st.caption("認証キーは返信やタイトル削除等に必要です。")
            submitted = st.form_submit_button("投稿")
    
    if submitted:
        existing_titles = {doc.to_dict().get("title") for doc in fetch_all_questions()
                           if not doc.to_dict().get("question", "").startswith("[SYSTEM]生徒はこの質問フォームを削除しました")}
        if new_title in existing_titles:
            st.error("このタイトルはすでに存在します。")
        elif not new_title or not new_text:
            st.error("タイトルと質問内容は必須です。")
        elif auth_key == "":
            st.error("認証キーは必須入力です。")
        else:
            poster_name = poster_name or "匿名"
            time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
            img_data = process_image(new_image) if new_image is not None else None
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
            st.rerun()

#####################################
# 質問一覧表示
#####################################
def show_title_list():
    st.title("📖 質問フォーラム")
    show_new_question_form()
    st.subheader("質問一覧")
    keyword_input = st.text_input("キーワード検索")
    keywords = [w.strip().lower() for w in keyword_input.split() if w.strip()] if keyword_input else []
    docs = fetch_all_questions()
    deleted_system_titles = {doc.to_dict().get("title") for doc in docs 
                             if doc.to_dict().get("question", "").startswith("[SYSTEM]生徒はこの質問フォームを削除しました")}
    title_info = {}
    for doc in docs:
        data = doc.to_dict()
        if data.get("question", "").startswith("[SYSTEM]"):
            continue
        title = data.get("title")
        poster = data.get("poster") or "匿名"
        auth_key = data.get("auth_key", "")
        timestamp = data.get("timestamp", "")
        if title in title_info:
            if timestamp < title_info[title]["orig_timestamp"]:
                title_info[title]["orig_timestamp"] = timestamp
                title_info[title]["poster"] = poster
                title_info[title]["auth_key"] = auth_key
            if timestamp > title_info[title]["update"]:
                title_info[title]["update"] = timestamp
        else:
            title_info[title] = {
                "poster": poster,
                "auth_key": auth_key,
                "orig_timestamp": timestamp,
                "update": timestamp
            }
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
    if keywords:
        def match(item):
            text = (item["title"] + " " + item["poster"]).lower()
            return all(kw in text for kw in keywords)
        distinct_titles = [item for item in distinct_titles if match(item)]
    distinct_titles.sort(key=lambda x: x["update"], reverse=True)
    if not distinct_titles:
        st.write("現在、質問はありません。")
    else:
        for idx, item in enumerate(distinct_titles):
            with st.container():
                title = item["title"]
                poster = item["poster"]
                update_time = item["update"]
                cols = st.columns([8, 2])
                label = f"{title}\n(投稿者: {poster})\n最終更新: {update_time}"
                if cols[0].button(label, key=f"title_button_{idx}"):
                    st.session_state.pending_auth_title = title
                    st.rerun()
                if cols[1].button("🗑", key=f"title_del_{idx}"):
                    st.session_state.pending_delete_title = title
                    st.rerun()
                if st.session_state.pending_auth_title == title:
                    st.markdown("---")
                    st.subheader(f"{title} の認証")
                    st.write("この質問にアクセスするには認証キーが必要です。")
                    with st.form(key=f"auth_form_{idx}"):
                        input_auth_key = st.text_input("認証キーを入力", type="password")
                        submit_auth = st.form_submit_button("認証する")
                        no_auth = st.form_submit_button("認証しないで閲覧する")
                        back = st.form_submit_button("戻る")
                    if submit_auth:
                        docs = fetch_questions_by_title(title)
                        if docs:
                            stored_auth_key = docs[0].to_dict().get("auth_key", "")
                            if input_auth_key == stored_auth_key:
                                st.session_state.selected_title = title
                                st.session_state.is_authenticated = True
                                st.session_state.pending_auth_title = None
                                st.success("認証に成功しました。")
                                st.rerun()
                            else:
                                st.error("認証キーが正しくありません。")
                    elif no_auth:
                        st.session_state.selected_title = title
                        st.session_state.is_authenticated = False
                        st.session_state.pending_auth_title = None
                        st.rerun()
                    elif back:
                        st.session_state.pending_auth_title = None
                        st.rerun()
                if st.session_state.pending_delete_title == title:
                    st.markdown("---")
                    st.subheader(f"{title} の削除確認")
                    st.write("このタイトルを削除してよろしいですか？")
                    with st.form(key=f"delete_form_{idx}"):
                        input_del_auth = st.text_input("認証キーを入力", type="password")
                        submit_del = st.form_submit_button("削除する")
                        cancel_del = st.form_submit_button("キャンセル")
                    if submit_del:
                        docs = fetch_questions_by_title(title)
                        if docs:
                            stored_auth_key = docs[0].to_dict().get("auth_key", "")
                            if input_del_auth == stored_auth_key:
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
                                st.cache_resource.clear()
                                docs_for_title = fetch_questions_by_title(title)
                                student_deleted = any(
                                    doc.to_dict().get("question", "").startswith("[SYSTEM]生徒はこの質問フォームを削除しました")
                                    for doc in docs_for_title
                                )
                                teacher_deleted = any(
                                    doc.to_dict().get("question", "").startswith("[SYSTEM]先生は質問フォームを削除しました")
                                    for doc in docs_for_title
                                )
                                if student_deleted and teacher_deleted:
                                    for doc in docs_for_title:
                                        db.collection("questions").document(doc.id).delete()
                                    st.success("両者による削除が確認されたため、データベースから完全に削除しました。")
                                st.cache_resource.clear()
                                st.rerun()
                            else:
                                st.error("認証キーが正しくありません。")
                    elif cancel_del:
                        st.session_state.pending_delete_title = None
                        st.rerun()
    if st.button("更新", key="title_update"):
        st.cache_resource.clear()
        st.rerun()

#####################################
# 質問詳細（チャットスレッド）の表示
#####################################
def show_chat_thread():
    selected_title = st.session_state.selected_title
    # タイトル部分：白背景コンテナを下に配置（上部に十分余白をとって背景の薄い水色が見える）
    st.markdown(
        f'<div style="background-color: white; padding: 10px; width: fit-content; margin: 40px auto 10px auto;"><h2>質問詳細: {selected_title}</h2></div>',
        unsafe_allow_html=True
    )
    # 詳細フォーラム全体の背景は薄い水色
    st.markdown(
        """
        <style>
        .block-container {
            background-color: #D3F7FF;
            padding: 20px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )   
    
    docs = fetch_questions_by_title(selected_title)
    first_question_poster = "匿名"
    if docs:
        first_question = docs[0].to_dict()
        first_question_poster = first_question.get("poster", "匿名")
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
        if msg_text.startswith("[先生]"):
            sender = "先生"
            msg_display = msg_text[len("[先生]"):].strip()
            align = "left"
            bg_color = "#FFFFFF"  # 先生は白背景
        else:
            sender = poster
            msg_display = msg_text
            align = "right"
            bg_color = "#DCF8C6"  # 生徒は緑背景
        # チャット枠の幅はテキストに合わせ、最大は80%
        st.markdown(
            f"""
            <div style="text-align: {align}; margin-bottom: 15px;">
              <div style="
                  display: inline-block;
                  background-color: {bg_color};
                  padding: 10px;
                  border-radius: 10px;
                  max-width: 80%;
                  word-wrap: break-word;">
                <b>{sender}:</b> {msg_display}<br>
                <small>({formatted_time})</small>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if "image" in data and data["image"]:
            img_data = base64.b64encode(data["image"]).decode("utf-8")
            # 画像コンテナ：背景色 #D3F7FF、幅80%、配置はチャットの寄せに合わせる
            align_style = "margin-left: auto;" if align=="right" else "margin-right: auto;"
            st.markdown(
                f'''
                <div style="text-align: {align}; margin-bottom: 15px; background-color: #D3F7FF; padding: 0;">
                    <img src="data:image/png;base64,{img_data}" style="width: 80%; height:auto; {align_style}">
                </div>
                ''',
                unsafe_allow_html=True
            )
        st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
     # 背景を変えたい範囲の開始
    st.markdown(
        """
        div[data-testid="stVerticalBlock"] {
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            }
            </style>
            """,
        unsafe_allow_html=True
    )   
    with st.container():
        if st.button("更新", key="chat_update"):
            st.cache_resource.clear()
            st.rerun()
        if st.session_state.is_authenticated:
            with st.expander("返信する", expanded=False):
                st.markdown('<div style="background-color: white; width: 100%; padding: 10px;">', unsafe_allow_html=True)
                with st.form("reply_form_student", clear_on_submit=True):
                    reply_text = st.text_area("メッセージを入力", key="reply_text")
                    reply_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"], key="reply_image")
                    submitted = st.form_submit_button("送信")
                    if submitted:
                        processed_reply = process_image(reply_image) if reply_image is not None else None
                        if not reply_text.strip() and not reply_image:
                            st.error("少なくともメッセージか画像を投稿してください。")
                        else:
                            time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
                            db.collection("questions").add({
                                "title": selected_title,
                                "question": reply_text.strip(),
                                "image": processed_reply,
                                "timestamp": time_str,
                                "deleted": 0,
                                "poster": first_question_poster
                            })
                            st.cache_resource.clear()
                            st.success("返信を送信しました！")
                            st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("認証されていないため返信はできません。")
        
        if st.button("戻る", key="chat_back"):
            st.session_state.selected_title = None
            st.rerun()
        
if st.session_state.selected_title is None:
    show_title_list()
else:
    show_chat_thread()
