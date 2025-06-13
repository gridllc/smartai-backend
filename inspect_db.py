import sqlite3

conn = sqlite3.connect("transcripts.db")
cursor = conn.cursor()

print("📄 Transcript Records:")
for row in cursor.execute("SELECT filename, LENGTH(transcript) FROM transcripts"):
    print(f"• {row[0]} — {row[1]} characters")

conn.close()