import qrcode
import streamlit as st
from io import BytesIO

# Streamlitのタイトル
st.title("QRコード生成")

# 生徒用ページのURL（StreamlitアプリのデプロイURLを指定）
forum_url = "https://student-forum.streamlit.app/"

# QRコードを生成
qr = qrcode.make(forum_url)

# QRコードをBytesIOに保存
qr_bytes = BytesIO()
qr.save(qr_bytes, format="PNG")
qr_bytes.seek(0)  # ファイルの先頭に移動

# QRコードを表示
st.image(qr_bytes, caption="生徒用ページのQRコード")

# ダウンロードリンクを表示
st.download_button("QRコードをダウンロード", qr_bytes, file_name="qr_code.png", mime="image/png")
