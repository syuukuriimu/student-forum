import os
import json
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

# Firebase 初期化
if not firebase_admin._apps:
    try:
        if os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
        else:
            service_account_info = json.loads(st.secrets["FIREBASE_SERVICE_ACCOUNT"])
            cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase 初期化エラー: {e}")

# Firestore クライアント
db = firestore.client()

st.title("👨‍🏫 先生用ダッシュボード")

# 先生用パスワード認証
password = st.text_input("🔑 パスワードを入力", type="password")
if password != "teacher123":
    st.error("🚫 パスワードが間違っています")
    st.stop()

st.success("✅ ログイン成功！")

# Firestore から質問一覧を取得
questions_ref = db.collection("questions").stream()
questions = [q.to_dict() | {"id": q.id} for q in questions_ref]

if not questions:
    st.info("📭 質問がまだありません")
else:
    for q in questions:
        st.write(f"📌 **質問:** {q['question']}")
        if q.get("image_url"):
            st.image(q["image_url"], caption="📷 添付画像", use_column_width=True)

        # 回答入力
        answer = st.text_area(f"💡 回答を入力 ({q['id']})")
        if st.button(f"✅ 回答を送信 ({q['id']})"):
            db.collection("questions").document(q["id"]).update({
                "answer": answer,
                "status": "answered"
            })
            st.success("✅ 回答を送信しました！")
            st.experimental_rerun()
        st.write("---")
