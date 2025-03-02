import streamlit as st

st.title("生徒用 質問ページ")

# 質問を投稿
question = st.text_area("質問を入力してください")
uploaded_file = st.file_uploader("画像をアップロード", type=["png", "jpg", "jpeg"])

if st.button("送信"):
    st.success("質問が送信されました！")
    # データを保存する処理（例: Firebase, JSONファイル, DBなど）

