import sqlite3

# データベース接続
conn = sqlite3.connect("questions.db")
cursor = conn.cursor()

# 質問テーブルの作成（修正済み）
cursor.execute("""
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    question TEXT,
    image BLOB,
    timestamp TEXT NOT NULL,
    deleted INTEGER DEFAULT 0  -- 削除フラグ（0: 未削除, 1: 削除済み）
)
""")

# `deleted` カラムがない場合は追加
try:
    cursor.execute("ALTER TABLE questions ADD COLUMN deleted INTEGER DEFAULT 0")
    conn.commit()
except sqlite3.OperationalError:
    pass  # 既にカラムが存在する場合はスキップ

# テストデータの追加（必要に応じてコメントアウト）
cursor.execute("INSERT INTO questions (title, question, timestamp, deleted) VALUES (?, ?, ?, ?)", 
               ("テスト質問", "これはテストメッセージです", "2025-03-04 17:00:00", 0))

conn.commit()
conn.close()

print("✅ データベースが作成・更新されました！")
