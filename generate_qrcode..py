import qrcode
import streamlit as st

st.title("QRコード生成")

url = st.text_input("QRコードにしたいURLを入力してください")
if st.button("生成"):
    img = qrcode.make(url)
    img.save("qrcode.png")
    st.image("qrcode.png", caption="QRコード")
