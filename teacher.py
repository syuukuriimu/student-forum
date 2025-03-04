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

if "selected_title" not in st.session_state:
    st.session_state.selected_title = None
if "pending_delete_msg_id" not in st.session_state:
    st.session_state.pending_delete_msg_id = None
if "pending_delete_title" not in st.session_state:
    st.session_state.pending_delete_title = None
# 先生側で削除したタイトルを記録するリスト
if "deleted_titles_teacher" not in st.session_state:
    st.session_state.deleted_titles_teacher = []

def show_title_list():
    st.title("📖 先生フォーラム")
    st.subheader("生徒からの質問一覧")

    cursor.execute("SELECT DISTINCT title FROM questions ORDER BY timestamp DESC")
    titles = cursor.fetchall()

    if not titles:
        st.write("現在、質問はありません。")
    else:
        for idx, (title,) in enumerate(titles):
            # 先生側で削除済みとしてマークされたタイトルは表示しない
            if title in st.session_state.deleted_titles_teacher:
                continue
            cols = st.columns([4, 1])
            if cols[0].button(title, key=f"title_button_{idx}"):
                st.session_state.selected_title = title
                st.rerun()
            if cols[1].button("🗑", key=f"title_del_{idx}"):
                st.session_state.pending_delete_title = title
            if st.session_state.get("pending_delete_title") == title:
                st.warning(f"本当にこのタイトルを削除しますか？")
                confirm_col1, confirm_col2 = st.columns(2)
                if confirm_col1.button("はい", key=f"confirm_delete_{idx}"):
                    st.session_state.pending_delete_title = None
                    st.session_state.deleted_titles_teacher.append(title)
                    # システムメッセージとして特別な接頭辞を付与して登録
                    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("INSERT INTO questions (title, question, timestamp, deleted) VALUES (?, ?, ?, 0)", 
                                   (title, "[SYSTEM]先生は質問フォームを削除しました", time_str))
                    conn.commit()
                    st.success("タイトルを削除しました。")
                    # 教員側と生徒側の両方で削除済みの場合、データベースから該当フォーラムを削除
                    cursor.execute("SELECT COUNT(*) FROM questions WHERE title = ? AND question = ?", (title, "[SYSTEM]生徒はこの質問フォームを削除しました"))
                    student_count = cursor.fetchone()[0]
                    if student_count > 0:
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
    st.title(f"質問詳細: {selected_title}")
    
    # システムメッセージを中央寄せの赤色テキストとして表示
    cursor.execute("SELECT question FROM questions WHERE title = ? AND question LIKE '[SYSTEM]%' ORDER BY timestamp ASC", (selected_title,))
    sys_msgs = cursor.fetchall()
    if sys_msgs:
        for sys_msg in sys_msgs:
            text = sys_msg[0][8:]  # "[SYSTEM]"を除去
            st.markdown(f"<h3 style='color: red; text-align: center;'>{text}</h3>", unsafe_allow_html=True)
    
    # 通常メッセージはシステムメッセージを除外して取得
    cursor.execute("SELECT id, question, image, timestamp, deleted FROM questions WHERE title = ? AND question NOT LIKE '[SYSTEM]%' ORDER BY timestamp", (selected_title,))
    records = cursor.fetchall()

    if records and all(rec[4] == 1 for rec in records):
        st.markdown("<h3 style='color: red;'>生徒はこのフォーラムを削除しました</h3>", unsafe_allow_html=True)

    if not records:
        st.write("該当する質問が見つかりません。")
        return

    for (msg_id, msg_text, msg_img, msg_time, deleted) in records:
        formatted_time = datetime.strptime(msg_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M")
        if deleted:
            st.markdown("<div style='color: red;'>【投稿が削除されました】</div>", unsafe_allow_html=True)
            continue

        is_teacher = msg_text.startswith("[先生]")
        sender = "自分" if is_teacher else "生徒"
        msg_display = msg_text[len("[先生]"):] if is_teacher else msg_text
        align = "right" if is_teacher else "left"
        bg_color = "#DCF8C6" if is_teacher else "#FFFFFF"

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
                  <img src="data:image/png;base64,{img_data}" style="max-width: 80%; height:auto;">
                </div>
                """,
                unsafe_allow_html=True
            )
        # 自分（先生）の投稿削除ボタンに削除確認を追加
        if is_teacher:
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
        with st.form("reply_form_teacher", clear_on_submit=True):
            reply_text = st.text_area("メッセージを入力")
            reply_image = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])
            submitted = st.form_submit_button("送信")

            if submitted and reply_text:
                teacher_message = "[先生] " + reply_text
                time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                img_data = reply_image.read() if reply_image else None
                cursor.execute(
                    "INSERT INTO questions (title, question, image, timestamp, deleted) VALUES (?, ?, ?, ?, 0)",
                    (selected_title, teacher_message, img_data, time_str)
                )
                conn.commit()
                st.success("返信を送信しました！")
                st.rerun()

    if st.button("戻る"):
        st.session_state.selected_title = None
        st.rerun()

if st.session_state.selected_title is None:
    show_title_list()
else:
    show_chat_thread()

conn.close()
