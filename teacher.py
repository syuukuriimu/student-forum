import streamlit as st

st.title("先生用 質問管理ページ")

# ここで生徒の質問を取得・表示
st.write("生徒の質問一覧")

# 仮の質問データ
questions = [
    {"text": "数学の問題が分かりません", "image": None},
    {"text": "歴史の宿題について教えてください", "image": None},
]

for q in questions:
    st.write(f"📌 {q['text']}")
    if q["image"]:
        st.image(q["image"], caption="添付画像")

if st.button("更新"):
    st.experimental_rerun()
