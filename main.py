from email_utils import send_email_with_attachment
from auth import get_current_user, authenticate_user, register_user, create_access_token
from pinecone_sdk import search_similar_chunks
from upload_processor import transcribe_audio, get_openai_client
from models import Base
from database import engine, get_db
import os
import shutil
import subprocess
import traceback
import io
import sqlite3
import json
from datetime import datetime
from collections import Counter
from zipfile import ZipFile

from fastapi import FastAPI, UploadFile, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from transcription_routes import router as transcription_router
app.include_router(transcription_router)


UPLOAD_DIR = "uploads"
TRANSCRIPT_DIR = "transcripts"
STATIC_DIR = "static"
DB_PATH = "transcripts.db"
ACTIVITY_LOG_PATH = "activity.log"


class AskRequest(BaseModel):
    question: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ResetPasswordRequest(BaseModel):
    email: str
    password: str
    code: str


def create_db_tables():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                action TEXT,
                filename TEXT,
                timestamp TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                question TEXT,
                answer TEXT,
                timestamp TEXT
            )
        """)
        conn.commit()


app = FastAPI()

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

Base.metadata.create_all(bind=engine)
create_db_tables()

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def log_activity(email: str, action: str, filename: str = None):
    timestamp = datetime.utcnow().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO activity (email, action, filename, timestamp) VALUES (?, ?, ?, ?)",
            (email, action, filename, timestamp)
        )
        conn.commit()
    with open(ACTIVITY_LOG_PATH, "a") as f:
        f.write(f"{timestamp}|{email}|{action}|{filename or ''}\n")


@app.get("/")
def read_root():
    return FileResponse("static/index.html")


@app.post("/register")
def register(payload: LoginRequest, db: Session = Depends(get_db)):
    register_user(db, payload.email, payload.password)
    return {"message": "User registered successfully"}


@app.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    token = create_access_token(data={"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/upload-and-transcribe")
async def upload_and_transcribe(file: UploadFile, user=Depends(get_current_user)):
    try:
        file_location = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_ext = os.path.splitext(file.filename)[1].lower()
        audio_file_path = file_location

        if file_ext in [".mp4", ".mov", ".mkv", ".avi"]:
            audio_file_path = file_location.rsplit(
                ".", 1)[0] + "_converted.wav"
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", file_location, "-vn", "-acodec",
                        "pcm_s16le", "-ar", "16000", "-ac", "1", audio_file_path],
                    check=True, capture_output=True, text=True
                )
            except subprocess.CalledProcessError as e:
                raise HTTPException(
                    status_code=500, detail=f"Audio extraction failed: {e.stderr}")
        elif file_ext not in [".wav", ".mp3", ".m4a", ".flac", ".ogg"]:
            raise HTTPException(
                status_code=400, detail=f"Unsupported file format: {file_ext}")

        transcript = transcribe_audio(audio_file_path)
        txt_path = os.path.join(
            TRANSCRIPT_DIR, os.path.basename(audio_file_path) + ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript)

        client = get_openai_client()
        summary_response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Summarize this transcript in 2–3 sentences."},
                {"role": "user", "content": transcript[:4000]}
            ],
            max_tokens=200,
            temperature=0.5
        )
        summary = summary_response.choices[0].message.content.strip()

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
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred during upload: {str(e)}")


@app.post("/ask")
async def stream_answer(request: AskRequest, user=Depends(get_current_user)):
    question = request.question
    chunks = search_similar_chunks(question, top_k=5)
    context = "\n\n".join([c["text"] for c in chunks])
    prompt = f"You are a helpful assistant. Use the following transcript snippets to answer the question.\n\n{context}\n\nQuestion: {question}"

    client = get_openai_client()
    stream = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.3,
        stream=True
    )

    answer_accumulator = []

    def event_generator():
        yield f"data: {json.dumps({'type': 'sources', 'data': chunks})}\n\n"
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                answer_accumulator.append(token)
                yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

    def save_qa_history_task():
        answer = ''.join(answer_accumulator).strip()
        if question and answer:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO qa_history (email, question, answer, timestamp) VALUES (?, ?, ?, ?)",
                    (user.email, question, answer, datetime.utcnow().isoformat())
                )
                conn.commit()

    log_activity(user.email, "ask")
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        background=BackgroundTask(save_qa_history_task)
    )


@app.get("/api/qa-history")
async def get_qa_history(user=Depends(get_current_user)):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT question, answer, timestamp FROM qa_history WHERE email = ? ORDER BY id DESC LIMIT 50",
            (user.email,)
        )
        history = [dict(row) for row in cursor.fetchall()]
    return {"history": history}


@app.get("/api/share/{filename}")
async def get_shared_transcript(filename: str):
    path = os.path.join(TRANSCRIPT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Transcript not found")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"transcript": content}


@app.get("/api/stats")
async def get_stats(user=Depends(get_current_user)):
    if not os.path.exists(ACTIVITY_LOG_PATH):
        return {"error": "Activity log not found."}
    with open(ACTIVITY_LOG_PATH, "r") as f:
        email_counts = Counter(line.split("|")[1] for line in f if "|" in line)
    return dict(email_counts)


@app.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    if payload.code != "smartai2024":
        raise HTTPException(status_code=401, detail="Invalid reset code")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET password = ? WHERE email = ?",
            (payload.password, payload.email)
        )
        conn.commit()
    return {"message": "Password updated successfully"}


@app.get("/api/download/all")
async def download_all_transcripts(user=Depends(get_current_user)):
    memory_file = io.BytesIO()
    with ZipFile(memory_file, 'w') as zipf:
        for filename in os.listdir(TRANSCRIPT_DIR):
            if filename.endswith(".txt"):
                filepath = os.path.join(TRANSCRIPT_DIR, filename)
                zipf.write(filepath, arcname=filename)
    memory_file.seek(0)
    headers = {"Content-Disposition": "attachment; filename=all_transcripts.zip"}
    return StreamingResponse(memory_file, media_type="application/zip", headers=headers)


@app.get("/api/activity-log")
async def get_activity_log(user=Depends(get_current_user)):
    if user.email != "patrick@gridllc.net":
        raise HTTPException(
            status_code=403, detail="Forbidden: Admin access required.")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT email, action, filename, timestamp FROM activity ORDER BY id DESC LIMIT 100")
        log_entries = [dict(row) for row in cursor.fetchall()]
    return {"log": log_entries}
