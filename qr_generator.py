import qrcode
import streamlit as st

# Streamlit のタイトル
st.title("QRコード生成")

# 生徒用ページのURL（StreamlitアプリのデプロイURLを指定）
forum_url = "https://student-forum.streamlit.app/"

# QRコードを生成
qr = qrcode.make(forum_url)

# QRコードを表示
st.image(qr.get_image(), caption="生徒用ページのQRコード")

# ダウンロードリンクを表示
qr.save("qr_code.png")
with open("qr_code.png", "rb") as f:
    st.download_button("QRコードをダウンロード", f, file_name="qr_code.png", mime="image/png")
