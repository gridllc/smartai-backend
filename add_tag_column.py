import sqlite3

conn = sqlite3.connect("transcripts.db")
c = conn.cursor()

try:
    c.execute("ALTER TABLE transcripts ADD COLUMN tag TEXT")
    print("✅ Column 'tag' added.")
except sqlite3.OperationalError as e:
    print("ℹ️ Might already exist:", e)

conn.commit()
conn.close()