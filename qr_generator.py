import streamlit as st
import qrcode
from io import BytesIO

st.title("📌 QRコード生成")

# フォーラムのURL（デプロイされた Streamlit Cloud の URL）
forum_url = "https://student-forum-lagceldzhkea3eve6puhtk.streamlit.app"

st.write(f"🔗 [質問フォーラム]({forum_url}) にアクセスしてください")

# QRコードを生成
def generate_qr_code(url):
    qr = qrcode.make(url)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return buf

qr_image = generate_qr_code(forum_url)
st.image(qr_image, caption="📌 質問フォーラム QRコード", use_column_width=True)
st.download_button("📥 QRコードをダウンロード", qr_image, "qr_code.png", "image/png")
