import streamlit as st
import os
from datetime import datetime

# 質問データを保存するフォルダ
SAVE_DIR = "questions"
os.makedirs(SAVE_DIR, exist_ok=True)

st.title("質問フォーラム")

# 画像アップロード
uploaded_file = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])

# メッセージ入力
message = st.text_area("質問内容を入力")

# 送信ボタン
if st.button("送信"):
    if uploaded_file and message:
        # ファイル名を作成（タイムスタンプ付き）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(SAVE_DIR, f"{timestamp}_{uploaded_file.name}")

        # 画像を保存
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # 質問のデータを保存（CSV）
        question_data = f"{timestamp},{file_path},{message}\n"
        with open(os.path.join(SAVE_DIR, "questions.csv"), "a", encoding="utf-8") as f:
            f.write(question_data)

        st.success("質問を送信しました！")
    else:
        st.warning("画像とメッセージを両方入力してください。")

# 質問一覧を表示
st.subheader("投稿された質問")

if os.path.exists(os.path.join(SAVE_DIR, "questions.csv")):
    with open(os.path.join(SAVE_DIR, "questions.csv"), "r", encoding="utf-8") as f:
        questions = f.readlines()

    for q in reversed(questions):  # 新しいものを上に表示
        timestamp, file_path, msg = q.strip().split(",", 2)
        st.image(file_path, caption=f"投稿日時: {timestamp}", use_column_width=True)
        st.write(f"**質問:** {msg}")
        st.markdown("---")
