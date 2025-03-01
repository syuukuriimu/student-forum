# Firebase 初期化のコード
import os
import json
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime


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
