import os
import shutil
import json
import subprocess
import traceback
import io
import sqlite3
import uuid
from datetime import datetime
from collections import Counter
from zipfile import ZipFile
from fastapi import FastAPI, UploadFile, Depends, HTTPException, Request, Form
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from database import engine, get_db
from models import Base
from upload_processor import transcribe_audio, get_openai_client
from pinecone_sdk import search_similar_chunks
from auth import get_current_user, authenticate_user, register_user, create_access_token
from email_utils import send_email_with_attachment

load_dotenv()

app = FastAPI()
Base.metadata.create_all(bind=engine)

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

class AskRequest(BaseModel):
    question: str

class LoginRequest(BaseModel):
    email: str
    password: str

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.post("/upload-and-transcribe")
async def upload_and_transcribe(file: UploadFile, user=Depends(get_current_user)):
    try:
        file_location = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"📁 Saved file to {file_location}")

        file_ext = os.path.splitext(file.filename)[1].lower()
        audio_file_path = file_location

        if file_ext in [".mp4", ".mov", ".mkv", ".avi"]:
            audio_file_path = file_location.rsplit(".", 1)[0] + "_converted.wav"
            try:
                print(f"🎬 Converting video {file.filename} to audio...")
                subprocess.run([
                    "ffmpeg", "-y", "-i", file_location,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    audio_file_path
                ], check=True, capture_output=True, text=True)
                print(f"🎧 Extracted audio to {audio_file_path}")
            except subprocess.CalledProcessError as e:
                print(f"❌ FFmpeg error: {e}")
                print(f"FFmpeg stderr: {e.stderr}")
                raise HTTPException(status_code=500, detail=f"Audio extraction failed: {e.stderr}")

        elif file_ext not in [".wav", ".mp3", ".m4a", ".flac", ".ogg"]:
            raise HTTPException(status_code=400, detail=f"Unsupported file format: {file_ext}")

        print(f"🎙️ Starting transcription of {os.path.basename(audio_file_path)}")
        transcript = transcribe_audio(audio_file_path)
        print(f"📝 Transcription completed: {len(transcript)} characters")

        txt_path = os.path.join(TRANSCRIPT_DIR, file.filename + ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript)
        print(f"💾 Transcript saved to {txt_path}")

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

        summary_path = txt_path.replace(".txt", "_summary.txt")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary)

        try:
            send_email_with_attachment(
                to_email=user.email,
                subject="Your SmartAI Transcript",
                body=f"Attached is your transcript for file: {file.filename}\n\nSummary:\n{summary}",
                file_path=txt_path
            )
        except Exception as email_error:
            print(f"⚠️ Email sending failed: {email_error}")

        log_activity(user.email, "upload", file.filename)

        return {"filename": file.filename, "transcript": transcript, "summary": summary}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Top-level error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/ask")
async def stream_answer(request: AskRequest, user=Depends(get_current_user)):
    question = request.question
    chunks = search_similar_chunks(question, top_k=5)
    context = "\n\n".join([c["text"] for c in chunks])
    prompt = (
        "You are a helpful assistant. Use the following transcript snippets to answer the question.\n\n"
        f"{context}\n\nQuestion: {question}"
    )

    client = get_openai_client()
    stream = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.3,
        stream=True
    )

    def event_generator():
        yield f"data: {json.dumps({'type': 'sources', 'data': chunks})}\n\n"
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

    log_activity(user.email, "ask")
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# NEW: API route to update transcript tags
@app.post("/api/transcript/{filename}/tag")
async def update_tag(filename: str, tag: str = Form(...)):
    conn = sqlite3.connect("transcripts.db")
    c = conn.cursor()
    c.execute("UPDATE transcripts SET tag = ? WHERE filename = ?", (tag, filename))
    conn.commit()
    conn.close()
    return {"message": "Tag saved"}

# NEW: API route to get shared transcripts
@app.get("/api/share/{filename}")
async def get_shared_transcript(filename: str):
    path = os.path.join("transcripts", filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Transcript not found")
    with open(path, "r") as f:
        return {"transcript": f.read()}

# NEW: Analytics route
@app.get("/api/stats")
def get_stats():
    from collections import Counter
    with open("activity.log", "r") as f:
        emails = [line.split("|")[1] for line in f.readlines()]
    return dict(Counter(emails))

@app.post("/reset-password")
async def reset_password(payload: dict):
    email = payload.get("email")
    password = payload.get("password")
    code = payload.get("code")
    if code != "smartai2024":
        raise HTTPException(status_code=401, detail="Invalid reset code")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET password = ? WHERE email = ?", (password, email))
    conn.commit()
    conn.close()
    return {"message": "Password updated"}

@app.get("/api/download/all")
async def download_all_transcripts(user=Depends(get_current_user)):
    memory_file = io.BytesIO()
    with ZipFile(memory_file, 'w') as zipf:
        for filename in os.listdir(TRANSCRIPT_DIR):
            if filename.endswith(".txt"):
                filepath = os.path.join(TRANSCRIPT_DIR, filename)
                zipf.write(filepath, arcname=filename)
    memory_file.seek(0)
    return StreamingResponse(memory_file, media_type="application/zip", headers={
        "Content-Disposition": "attachment; filename=all_transcripts.zip"
    })

@app.get("/api/activity-log")
async def get_activity_log(user=Depends(get_current_user)):
    if user.email != "patrick@gridllc.net":
        raise HTTPException(status_code=403, detail="Admins only")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            action TEXT,
            filename TEXT,
            timestamp TEXT
        )
    """)
    c.execute("SELECT email, action, filename, timestamp FROM activity ORDER BY id DESC LIMIT 100")
    rows = c.fetchall()
    conn.close()
    return {"log": rows}

def log_activity(email, action, filename=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            action TEXT,
            filename TEXT,
            timestamp TEXT
        )
    """)
    c.execute("INSERT INTO activity (email, action, filename, timestamp) VALUES (?, ?, ?, ?)",
              (email, action, filename, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    
    # Also log to activity.log file for analytics
    with open("activity.log", "a") as f:
        f.write(f"{datetime.utcnow().isoformat()}|{email}|{action}|{filename or ''}\n")

@app.post("/register")
def register(payload: LoginRequest, db: Session = Depends(get_db)):
    register_user(db, payload.email, payload.password)
    return {"message": "User registered successfully"}

@app.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    token = create_access_token(data={"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/api/history")
async def history(user=Depends(get_current_user)):
    filenames = []
    if os.path.exists(TRANSCRIPT_DIR):
        for name in os.listdir(TRANSCRIPT_DIR):
            if name.endswith(".txt"):
                filenames.append(name.replace(".txt", ""))
    return {"files": filenames}

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
   
@app.get("/share/{filename}")
async def share_transcript(filename: str):
    path = os.path.join("transcripts", filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Transcript not found")
    with open(path, "r", encoding="utf-8") as f:  # <- Fixed indentation
        return {"transcript": f.read()}