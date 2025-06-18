import os
from fastapi import FastAPI, UploadFile, Depends, HTTPException, Header, Request, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import shutil
import subprocess
import smtplib
from email.message import EmailMessage
from sqlalchemy.orm import Session

from dotenv import load_dotenv
from database import engine, get_db
from models import Base
from upload_processor import transcribe_audio, get_openai_client
from pinecone_sdk import search_similar_chunks
from auth import get_current_user, authenticate_user, register_user, create_access_token

load_dotenv()

# --- Init app and DB ---
app = FastAPI()
Base.metadata.create_all(bind=engine)
print("✅ Tables created in PostgreSQL")

# --- Directories ---
UPLOAD_DIR = "uploads"
TRANSCRIPT_DIR = "transcripts"
STATIC_DIR = "static"
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

# --- Pydantic models ---
class AskRequest(BaseModel):
    question: str

class LoginRequest(BaseModel):
    email: str
    password: str

# --- Root endpoint ---
@app.get("/")
def read_root():
    return FileResponse("static/index.html")

# --- Upload and Transcribe ---
@app.post("/upload-and-transcribe")
async def upload_and_transcribe(file: UploadFile, user=Depends(get_current_user)):
    try:
        file_location = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"📁 Saved file to {file_location}")

        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext in [".mp4", ".mov", ".mkv", ".avi"]:
            audio_path = file_location.rsplit(".", 1)[0] + "_audio.wav"
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", file_location,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    audio_path
                ], check=True)
                print(f"🎧 Extracted audio to {audio_path}")
                file_location = audio_path
            except subprocess.CalledProcessError as e:
                print(f"❌ FFmpeg error: {e}")
                raise HTTPException(status_code=500, detail="Audio extraction failed")

        transcript = transcribe_audio(file_location)
        print(f"🖍️ Transcript result: {transcript[:100]}...")

        txt_path = os.path.join(TRANSCRIPT_DIR, file.filename + ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript)

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

        send_email_with_attachment(
            to_email=user.email,
            subject="Your SmartAI Transcript",
            body=f"Attached is your transcript for file: {file.filename}\n\nSummary:\n{summary}",
            file_path=txt_path
        )

        return {"filename": file.filename, "transcript": transcript, "summary": summary}

    except Exception as e:
        print(f"❌ Top-level error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")

# --- Email Utility ---
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

# --- Ask a Question ---
@app.post("/ask")
async def ask_question(request: AskRequest, user=Depends(get_current_user)):
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
    return {"answer": answer, "sources": relevant_chunks}

# --- Auth Routes ---
@app.post("/register")
def register(payload: LoginRequest, db: Session = Depends(get_db)):
    register_user(db, payload.email, payload.password)
    return {"message": "User registered successfully"}

@app.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    token = create_access_token(data={"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

# --- Static file routes ---
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
