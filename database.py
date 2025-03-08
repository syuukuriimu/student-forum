import os
import sqlite3

# データベースの削除
if os.path.exists("questions.db"):
    os.remove("questions.db")
    print("✅ 古いデータベースを削除しました。")
else:
    print("⚠️ データベースは存在しませんでした。")

# データベースの再作成
conn = sqlite3.connect("questions.db")
cursor = conn.cursor()

# `questions` テーブルの再作成
cursor.execute("""
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 質問ID
    title TEXT NOT NULL,                   -- 質問のタイトル
    question TEXT,                         -- 質問の詳細
    image BLOB,                            -- 質問の画像
    timestamp TEXT NOT NULL,               -- タイムスタンプ
    deleted INTEGER DEFAULT 0,             -- 削除フラグ（0: 未削除, 1: 削除済み）
    username TEXT DEFAULT 'anonymous',     -- ユーザー名（匿名時は 'anonymous'）
    answer TEXT,                           -- 先生の回答
    answer_image BLOB,                     -- 先生の回答の画像
    status TEXT,                           -- 質問のステータス
    student_reply TEXT                     -- 生徒の返信
)
""")

# テストデータの追加
cursor.execute("""
INSERT INTO questions (
    title, question, timestamp, deleted, username, answer, answer_image, status, student_reply
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", 
(
    "テスト質問", "これはテストメッセージです", 
    "2025-03-04 17:00:00", 0, 
    "anonymous", "サンプル回答", None, 
    "回答済み", "サンプル返信"
))

conn.commit()
conn.close()

print("✅ 新しいデータベースが作成されました。")
