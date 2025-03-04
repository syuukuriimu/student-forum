import qrcode
import streamlit as st

# Streamlitのタイトル
st.title("QRコード生成")

# 生徒用ページのURL（StreamlitアプリのデプロイURLを指定）
forum_url = "https://student-forum.streamlit.app/"

# QRコードを生成
qr = qrcode.make(forum_url)

# QRコードを表示
st.image(qr, caption="生徒用ページのQRコード")

# QRコードを保存
qr.save("qr_code.png")

# ダウンロードリンクを表示
with open("qr_code.png", "rb") as f:
    st.download_button("QRコードをダウンロード", f, file_name="qr_code.png", mime="image/png")