import streamlit as st
import base64
from datetime import datetime
from zoneinfo import ZoneInfo  # タイムゾーン設定用
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

# --- 投稿者認証のUI ---
def show_authentication_ui(title):
    st.info("この質問に対して投稿者認証を行いますか？")
    col1, col2 = st.columns(2)
    if col1.button("認証する", key=f"auth_yes_{title}"):
        st.session_state.authenticated_questions[title] = "pending"  # 後でパスワード入力させる
        st.session_state.selected_title = title  # 質問タイトルを選択
        st.rerun()  # 画面を再表示
    if col2.button("認証せずに閲覧", key=f"auth_no_{title}"):
        st.session_state.authenticated_questions[title] = False
        st.session_state.selected_title = title  # 質問タイトルを選択
        st.rerun()  # 画面を再表示

# --- 投稿者認証のチェック（パスワード入力） ---
def check_authentication(title):
    # 既に認証済み（True または False）ならその状態を返す
    if title in st.session_state.authenticated_questions and st.session_state.authenticated_questions[title] != "pending":
        return st.session_state.authenticated_questions[title]

    # 認証未選択の場合は、認証UIを表示
    if title not in st.session_state.authenticated_questions:
        show_authentication_ui(title)
        return None

    # 「認証する」を選択して "pending" 状態なら、パスワード入力フォームを表示
    if st.session_state.authenticated_questions.get(title) == "pending":
        st.info("投稿者パスワードを入力してください。")
        auth_pw = st.text_input("投稿者パスワード", type="password", key=f"auth_pw_{title}")
        if st.button("認証", key=f"auth_btn_{title}"):
            # Firestore から対象タイトルの最初の投稿のパスワードを取得
            docs = fetch_questions_by_title(title)
            poster_pw = None
            for doc in docs:
                data = doc.to_dict()
                # 最初の通常投稿（システムメッセージでない）から取得
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

# 詳細フォーラムページに進む処理
def go_to_forum_page(title):
    authentication_status = check_authentication(title)
    if authentication_status is True:
        # 認証に成功した場合、詳細フォーラムに進む処理
        st.write(f"質問タイトル: {title} の詳細フォーラムに進みます。")
        # ここで詳細フォーラムページの内容を表示する処理を追加
    elif authentication_status is False:
        # 認証なしで閲覧の場合、詳細フォーラムに進む処理
        st.write(f"質問タイトル: {title} の詳細フォーラムに進みます（認証なし）。")
        # ここで詳細フォーラムページの内容を表示する処理を追加

# --- 質問タイトル一覧の表示 ---
def show_title_list():
    st.title("📖 質問フォーラム")
    st.subheader("質問一覧")
    
    # 新規質問投稿ボタン
    if st.button("＋ 新規質問を投稿"):
        st.session_state.selected_title = "__new_question__"
        st.rerun()
    
    # キーワード検索
    keyword = st.text_input("キーワード検索")
    
    docs = fetch_all_questions()
    # 削除された質問タイトル（システムメッセージ）を除外
    deleted_titles = set()
    for doc in docs:
        data = doc.to_dict()
        if data.get("question", "").startswith("[SYSTEM]投稿者はこの質問フォームを削除しました"):
            deleted_titles.add(data.get("title"))
    
    # 各タイトルの投稿者情報を取得（最初の通常投稿）
    title_info = {}
    for doc in docs:
        data = doc.to_dict()
        title = data.get("title")
        if title in title_info:
            continue
        if not data.get("question", "").startswith("[SYSTEM]"):
            poster = data.get("poster", "不明")
            title_info[title] = poster
    # 削除済みタイトルを除外
    distinct_titles = {t: poster for t, poster in title_info.items() if t not in deleted_titles}
    
    # キーワードフィルタ（タイトルまたは投稿者名に一致）
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
            # タイトル削除は、操作前に投稿者認証を求める（認証済みなら削除可能）
            if cols[1].button("🗑", key=f"title_del_{idx}"):
                auth = check_authentication(title)
                if auth is True:
                    st.session_state.pending_delete_title = title
                    st.rerun()
    
    # タイトル削除確認
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

# --- 詳細フォーラム（チャットスレッド）の表示 ---
def show_chat_thread():
    selected_title = st.session_state.selected_title
    if selected_title == "__new_question__":
        create_new_question()
        return
    
    st.title(f"質問詳細: {selected_title}")
    
    docs = fetch_questions_by_title(selected_title)
    
    # システムメッセージ（中央寄せの赤字）の表示
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
        
        # 先生の返信は "[先生]" で、投稿者の投稿はそのまま
        if msg_text.startswith("[先生]"):
            sender = "先生"
            is_own = False
            msg_display = msg_text[len("[先生]"):].strip()
            align = "left"
            bg_color = "#FFFFFF"
        else:
            sender = "自分"
            msg_display = msg_text
            # ※ 認証済み（True）の場合は、個別削除は行わず、タイトル削除のみ可能とする
            if st.session_state.authenticated_questions.get(selected_title) is True:
                is_own = False
            else:
                is_own = True
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
                f'''
                <div style="text-align: {align}; margin-bottom: 15px;">
                    <img src="data:image/png;base64,{img_data}" style="max-width: 80%; height:auto;">
                </div>
                ''',
                unsafe_allow_html=True
            )
        st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
        
        # 個別削除ボタンは、認証していない場合のみ表示
        if is_own and st.session_state.authenticated_questions.get(selected_title) is not True:
            if st.button("🗑", key=f"del_{msg_id}"):
                st.session_state.pending_delete_msg_id = msg_id
                st.rerun()
        if st.session_state.pending_delete_msg_id == msg_id:
            st.warning("本当にこの投稿を削除しますか？")
            col1, col2 = st.columns(2)
            if col1.button("はい", key=f"confirm_delete_{msg_id}"):
                doc_ref = db.collection("questions").document(msg_id)
                doc_ref.update({"deleted": 1})
                st.session_state.pending_delete_msg_id = None
                st.cache_resource.clear()
                st.rerun()
            if col2.button("キャンセル", key=f"cancel_delete_{msg_id}"):
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
    if st.button("更新"):
        st.cache_resource.clear()
        st.rerun()
    
    # 返信フォーム（認証済みの場合のみ表示）
    if st.session_state.authenticated_questions.get(selected_title) is True:
        with st.expander("返信する", expanded=False):
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
                        "timestamp": time_str,
                        "deleted": 0
                    })
                    st.cache_resource.clear()
                    st.success("返信を送信しました！")
                    st.rerun()
    else:
        st.info("返信やタイトル削除を行うには、上部で投稿者認証を行ってください。")
    
    if st.button("戻る"):
        st.session_state.selected_title = None
        st.rerun()

# --- 新規質問投稿フォーム ---
def create_new_question():
    st.title("新規質問を投稿")
    with st.form("new_question_form", clear_on_submit=True):
        new_title = st.text_input("質問のタイトルを入力")
        new_text = st.text_area("質問内容を入力")
        new_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
        poster_name = st.text_input("投稿者名を入力（未入力の場合は匿名）", value="匿名")
        poster_password = st.text_input("投稿者用パスワードを設定", type="password")
        submitted = st.form_submit_button("投稿")
        if submitted and new_title and new_text and poster_password:
            time_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
            img_data = new_image.read() if new_image else None
            db.collection("questions").add({
                "title": new_title,
                "question": new_text,
                "image": img_data,
                "timestamp": time_str,
                "deleted": 0,
                "poster": poster_name,
                "poster_password": poster_password
            })
            # 初回は投稿者認証済み状態とする（以降はユーザーが認証の選択を行う）
            st.session_state.authenticated_questions[new_title] = True
            st.cache_resource.clear()
            st.success("質問を投稿しました！")
            st.session_state.selected_title = new_title
            st.rerun()
    if st.button("戻る"):
        st.session_state.selected_title = None
        st.rerun()

# --- メイン表示の切り替え ---
if st.session_state.selected_title is None:
    show_title_list()
else:
    show_chat_thread()
