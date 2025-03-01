import os
import json
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage

# Firebase 初期化（デプロイ環境でも動作するように修正）
if not firebase_admin._apps:
    try:
        if os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
        else:
            service_account_info = json.loads(st.secrets["FIREBASE_SERVICE_ACCOUNT"])
            cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {"storageBucket": "your-firebase-bucket-name.appspot.com"})
    except Exception as e:
        st.error(f"Firebase 初期化エラー: {e}")

# Firestore クライアント
db = firestore.client()

# Storage クライアント
bucket = storage.bucket()

st.title("📩 質問フォーラム")

# フォーム入力
with st.form(key="question_form"):
    question = st.text_area("💬 質問を入力してください")
    image = st.file_uploader("📷 画像をアップロード（オプション）", type=["jpg", "jpeg", "png"])
    submit_button = st.form_submit_button(label="質問を送信")

    if submit_button:
        if not question:
            st.error("⚠ 質問を入力してください！")
        else:
            # Firestore にデータを追加
            doc_ref = db.collection("questions").add({
                "question": question,
                "status": "unanswered",
                "image_url": None
            })

            # 画像アップロード
            doc_id = doc_ref[1].id
            if image:
                blob = bucket.blob(f"questions/{doc_id}/{image.name}")
                blob.upload_from_file(image)
                blob.make_public()
                image_url = blob.public_url

                # Firestore に画像URLを保存
                db.collection("questions").document(doc_id).update({"image_url": image_url})

            st.success("✅ 質問が送信されました！")
            st.experimental_rerun()
