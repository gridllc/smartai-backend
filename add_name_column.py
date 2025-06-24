import sqlite3

db_path = "C:\\Users\\pgrif\\AI_Projects\\smartai_backend\\transcripts.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE users ADD COLUMN name TEXT;")
    print("✅ 'name' column added to 'users' table.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("⚠️ Column 'name' already exists.")
    else:
        print("❌ Error:", e)

conn.commit()
conn.close()
