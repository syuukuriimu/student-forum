import sqlite3  
import streamlit as st
import base64
from datetime import datetime

conn = sqlite3.connect("questions.db", check_same_thread=False)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE questions ADD COLUMN deleted INTEGER DEFAULT 0")
    conn.commit()
except sqlite3.OperationalError:
    pass

# 新しい API を優先し、なければ旧 API を使用する
try:
    query_params = st.query_params
except AttributeError:
    query_params = st.experimental_get_query_params()

try:
    set_query_params = st.set_query_params
except AttributeError:
    set_query_params = st.experimental_set_query_params

# クエリパラメータから selected_title を取得し、セッションに反映
if "selected_title" in query_params:
    st.session_state.selected_title = query_params["selected_title"][0]
else:
    if "selected_title" not in st.session_state:
        st.session_state.selected_title = None

if "pending_delete_msg_id" not in st.session_state:
    st.session_state.pending_delete_msg_id = None
if "pending_delete_title" not in st.session_state:
    st.session_state.pending_delete_title = None
# 生徒側で削除したタイトルを記録するリスト
if "deleted_titles_student" not in st.session_state:
    st.session_state.deleted_titles_student = []

def show_title_list():
    st.title("📖 質問フォーラム")
    st.subheader("質問一覧")

    if st.button("＋ 新規質問を投稿"):
        st.session_state.selected_title = "__new_question__"
        set_query_params(selected_title="__new_question__")
        st.rerun()
    
    cursor.execute("SELECT DISTINCT title FROM questions ORDER BY timestamp DESC")
    titles = cursor.fetchall()
    
    if not titles:
        st.write("現在、質問はありません。")
    else:
        for idx, (title,) in enumerate(titles):
            # 生徒側で削除済みとしてマークされたタイトルは表示しない
            if title in st.session_state.deleted_titles_student:
                continue
            cols = st.columns([4, 1])
            if cols[0].button(title, key=f"title_button_{idx}"):
                st.session_state.selected_title = title
                set_query_params(selected_title=title)
                st.rerun()
            if cols[1].button("🗑", key=f"title_del_{idx}"):
                st.session_state.pending_delete_title = title
            if st.session_state.get("pending_delete_title") == title:
                st.warning(f"本当にこのタイトルを削除しますか？")
                confirm_col1, confirm_col2 = st.columns(2)
                if confirm_col1.button("はい", key=f"confirm_delete_{idx}"):
                    st.session_state.pending_delete_title = None
                    st.session_state.deleted_titles_student.append(title)
                    # システムメッセージとして特別な接頭辞を付与して登録
                    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("INSERT INTO questions (title, question, timestamp, deleted) VALUES (?, ?, ?, 0)", 
                                   (title, "[SYSTEM]生徒はこの質問フォームを削除しました", time_str))
                    conn.commit()
                    st.success("タイトルを削除しました。")
                    # チャット履歴に対して、相手側（先生）の削除システムメッセージが既に登録されている場合、両側削除と判断してデータベースから削除
                    cursor.execute("SELECT COUNT(*) FROM questions WHERE title = ? AND question = ?", (title, "[SYSTEM]先生は質問フォームを削除しました"))
                    teacher_count = cursor.fetchone()[0]
                    if teacher_count > 0:
                        cursor.execute("DELETE FROM questions WHERE title = ?", (title,))
                        conn.commit()
                    st.rerun()
                if confirm_col2.button("キャンセル", key=f"cancel_delete_{idx}"):
                    st.session_state.pending_delete_title = None
                    st.rerun()
    
    if st.button("更新"):
        st.rerun()

def show_chat_thread():
    selected_title = st.session_state.selected_title
    if selected_title == "__new_question__":
        create_new_question()
        return
    
    st.title(f"質問詳細: {selected_title}")
    
    # システムメッセージを中央寄せの赤色テキストとして表示（チャット形式ではなく）
    cursor.execute("SELECT question FROM questions WHERE title = ? AND question LIKE '[SYSTEM]%' ORDER BY timestamp ASC", (selected_title,))
    sys_msgs = cursor.fetchall()
    if sys_msgs:
        for sys_msg in sys_msgs:
            text = sys_msg[0][8:]  # "[SYSTEM]"を除去
            st.markdown(f"<h3 style='color: red; text-align: center;'>{text}</h3>", unsafe_allow_html=True)
    
    # 通常メッセージはシステムメッセージを除外して取得
    cursor.execute("SELECT id, question, image, timestamp, deleted FROM questions WHERE title = ? AND question NOT LIKE '[SYSTEM]%' ORDER BY timestamp", (selected_title,))
    records = cursor.fetchall()

    if records and all(rec[4] == 2 for rec in records):
        st.markdown("<h3 style='color: red;'>先生はこのフォーラムを削除しました</h3>", unsafe_allow_html=True)
    else:
        if not records:
            st.write("該当する質問が見つかりません。")
            return
        for (msg_id, msg_text, msg_img, msg_time, deleted) in records:
            formatted_time = datetime.strptime(msg_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M")
            if deleted:
                st.markdown("<div style='color: red;'>【投稿が削除されました】</div>", unsafe_allow_html=True)
                continue
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
            # 自分の投稿の削除ボタンに削除確認を追加
            if is_self:
                if st.button("🗑", key=f"del_{msg_id}"):
                    st.session_state.pending_delete_msg_id = msg_id
                if st.session_state.get("pending_delete_msg_id") == msg_id:
                    st.warning("本当にこの投稿を削除しますか？")
                    confirm_col1, confirm_col2 = st.columns(2)
                    if confirm_col1.button("はい", key=f"confirm_del_{msg_id}"):
                        st.session_state.pending_delete_msg_id = None
                        cursor.execute("UPDATE questions SET deleted = 1 WHERE id = ?", (msg_id,))
                        conn.commit()
                        st.rerun()
                    if confirm_col2.button("キャンセル", key=f"cancel_del_{msg_id}"):
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
        st.rerun()
    with st.expander("返信する"):
        with st.form("reply_form_student", clear_on_submit=True):
            reply_text = st.text_area("メッセージを入力")
            reply_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
            submitted = st.form_submit_button("送信")
            if submitted:
                time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                img_data = reply_image.read() if reply_image else None
                cursor.execute(
                    "INSERT INTO questions (title, question, image, timestamp, deleted) VALUES (?, ?, ?, ?, 0)",
                    (selected_title, reply_text, img_data, time_str)
                )
                conn.commit()
                st.success("返信を送信しました！")
                st.rerun()
    if st.button("戻る"):
        st.session_state.selected_title = None
        set_query_params(selected_title=None)
        st.rerun()

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
            cursor.execute(
                "INSERT INTO questions (title, question, image, timestamp, deleted) VALUES (?, ?, ?, ?, 0)",
                (new_title, new_text, img_data, time_str)
            )
            conn.commit()
            st.success("質問を投稿しました！")
            st.session_state.selected_title = new_title
            set_query_params(selected_title=new_title)
            st.rerun()
    if st.button("戻る"):
        st.session_state.selected_title = None
        set_query_params(selected_title=None)
        st.rerun()

if st.session_state.selected_title is None:
    show_title_list()
else:
    show_chat_thread()

conn.close()
