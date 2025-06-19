import sqlite3

DB_PATH = "transcripts.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS qa_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    timestamp TEXT NOT NULL
)
""")

conn.commit()
conn.close()

print("✅ qa_history table created or already exists.")
