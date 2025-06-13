import os

TRANSCRIPT_DIR = "transcripts"
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

def save_transcript(filename: str, text: str):
    filepath = os.path.join(TRANSCRIPT_DIR, filename + ".txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)

def get_transcript_text(filename: str) -> dict:
    filepath = os.path.join(TRANSCRIPT_DIR, filename + ".txt")
    with open(filepath, "r", encoding="utf-8") as f:
        return {"text": f.read()}
