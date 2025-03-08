import sqlite3

# データベース接続
try:
    conn = sqlite3.connect("questions.db")
    cursor = conn.cursor()

    # データベースのカラム構造を確認
    cursor.execute("PRAGMA table_info(questions);")
    columns = cursor.fetchall()

    # 結果を見やすく表示
    print("✅ データベースのカラム構造")
    for column in columns:
        print(f"・{column[1]} ({column[2]})")

except sqlite3.Error as e:
    print(f"❌ データベースエラー: {e}")

finally:
    if conn:
        conn.close()
