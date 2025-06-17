import os
import sqlite3
from fastapi import FastAPI, UploadFile, Depends, HTTPException, Header, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
from datetime import datetime
from upload_processor import transcribe_audio, get_openai_client
from pinecone_sdk import search_similar_chunks
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import subprocess

load_dotenv()

app = FastAPI()

UPLOAD_DIR = "uploads"
TRANSCRIPT_DIR = "transcripts"
STATIC_DIR = "static"
DB_PATH = "transcripts.db"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS transcripts (
        filename TEXT PRIMARY KEY,
        transcript TEXT,
        timestamp TEXT,
        summary TEXT
    )""")

    c.execute("DROP TABLE IF EXISTS users")
    c.execute("""CREATE TABLE users (
        email TEXT PRIMARY KEY,
        password TEXT
    )""")

    c.execute("INSERT INTO users (email, password) VALUES (?, ?)", ("patrick@gridllc.net", "1Password"))
    c.execute("INSERT INTO users (email, password) VALUES (?, ?)", ("davidgriffin99@gmail.com", "2Password"))

    c.execute("""CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        filename TEXT,
        question TEXT,
        answer TEXT,
        asked_at TEXT
    )""")

    conn.commit()
    conn.close()

class AskRequest(BaseModel):
    question: str

class LoginRequest(BaseModel):
    email: str
    password: str

def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    token = authorization.replace("Bearer ", "")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE email = ?", (token,))
    user = c.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return token

@app.post("/login")
async def login(payload: LoginRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE email = ?", (payload.email,))
    row = c.fetchone()
    conn.close()
    if not row or row[0] != payload.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": payload.email}

@app.post("/register")
async def register(payload: LoginRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE email = ?", (payload.email,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="User already exists")
    c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (payload.email, payload.password))
    conn.commit()
    conn.close()
    return {"message": "User registered"}

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

def send_email_with_attachment(to_email, subject, body, file_path):
    try:
        msg = EmailMessage()
        msg["From"] = os.getenv("EMAIL_USER")
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        with open(file_path, "rb") as f:
            file_data = f.read()
            file_name = os.path.basename(file_path)

        msg.add_attachment(file_data, maintype="text", subtype="plain", filename=file_name)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
            smtp.send_message(msg)

        print(f"📧 Email sent to {to_email} with {file_name}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

@app.post("/upload-and-transcribe")
async def upload_and_transcribe(file: UploadFile, user: str = Depends(verify_token)):
    file_location = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    print(f"📁 Saved file to {file_location}")

    # ✅ Extract audio if it's a video file
    if file.filename.lower().endswith((".mp4", ".mov", ".mkv", ".avi")):
        audio_path = file_location.rsplit(".", 1)[0] + "_audio.wav"
        try:
            subprocess.run([
                "ffmpeg", "-i", file_location,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                audio_path
            ], check=True)
            print(f"🎧 Extracted audio to {audio_path}")
            file_location = audio_path
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg failed: {e}")
            raise HTTPException(status_code=500, detail="Audio extraction failed")

    try:
        transcript = transcribe_audio(file_location)
        print(f"📝 Transcript result: {transcript[:100]}...")
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")

    try:
        txt_path = os.path.join(TRANSCRIPT_DIR, file.filename + ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript)
        print(f"✅ Transcript written to {txt_path}")
    except Exception as e:
        print(f"❌ Writing transcript failed: {e}")
        raise HTTPException(status_code=500, detail="Saving transcript failed")

    try:
        client = get_openai_client()
        summary_response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Summarize this transcript in 2–3 sentences."},
                {"role": "user", "content": transcript[:3000]}
            ],
            max_tokens=200,
            temperature=0.5
        )
        summary = summary_response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ GPT Summary failed: {e}")
        summary = "(Summary unavailable)"

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("REPLACE INTO transcripts (filename, transcript, timestamp, summary) VALUES (?, ?, ?, ?)",
                  (file.filename, transcript, datetime.utcnow().isoformat(), summary))
        conn.commit()
        conn.close()
        print(f"📦 Transcript + summary saved to DB for {file.filename}")
    except Exception as e:
        print(f"❌ DB insert failed: {e}")
        raise HTTPException(status_code=500, detail="Database write failed")

    send_email_with_attachment(
        to_email=user,
        subject="Your SmartAI Transcript",
        body=f"Attached is your transcript for file: {file.filename}\n\nSummary:\n{summary}",
        file_path=txt_path
    )

    return {"filename": file.filename, "transcript": transcript, "summary": summary}

@app.get("/api/history")
async def history(user: str = Depends(verify_token)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT filename, timestamp, summary FROM transcripts")
    rows = c.fetchall()
    conn.close()
    return {"files": [{"filename": r[0], "timestamp": r[1], "summary": r[2]} for r in rows]}

@app.get("/api/transcript/{filename}")
async def get_transcript(filename: str, user: str = Depends(verify_token)):
    filepath = os.path.join(TRANSCRIPT_DIR, filename + ".txt")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return {"filename": filename, "transcript": f.read()}
    return JSONResponse(status_code=404, content={"error": "Transcript not found"})

@app.get("/api/download/{filename}")
async def download_transcript(filename: str, user: str = Depends(verify_token)):
    filepath = os.path.join(TRANSCRIPT_DIR, filename + ".txt")
    if os.path.exists(filepath):
        return FileResponse(filepath, media_type='application/octet-stream', filename=filename + ".txt")
    return JSONResponse(status_code=404, content={"error": "Transcript file not found"})

@app.delete("/api/delete/{filename}")
async def delete_transcript(filename: str, user: str = Depends(verify_token)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM transcripts WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()

    txt_path = os.path.join(TRANSCRIPT_DIR, filename + ".txt")
    if os.path.exists(txt_path):
        os.remove(txt_path)

    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    return {"status": "deleted"}

@app.post("/ask")
async def ask_question(request: AskRequest, user: str = Depends(verify_token)):
    question = request.question
    relevant_chunks = search_similar_chunks(question, top_k=5)
    context_block = "\n\n".join([chunk["text"] for chunk in relevant_chunks])
    system_prompt = (
        "You are a helpful assistant. Use the following transcript snippets to answer the question.\n\n"
        f"{context_block}\n\n"
        "Question: " + question
    )
    client = get_openai_client()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": system_prompt}],
        temperature=0.3,
        max_tokens=500
    )
    answer = response.choices[0].message.content

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO questions (user, filename, question, answer, asked_at) VALUES (?, ?, ?, ?, ?)",
              (user, "contextual", question, answer, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    return {"answer": answer, "sources": relevant_chunks}

@app.get("/uploads/{filename}")
async def get_uploaded_file(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return JSONResponse(status_code=404, content={"error": "File not found"})

@app.get("/static/{filename}")
async def get_static_file(filename: str):
    file_path = os.path.join(STATIC_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return JSONResponse(status_code=404, content={"error": "File not found"})

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print("🔧 transcripts.db not found. Initializing fresh database.")
        init_db()
