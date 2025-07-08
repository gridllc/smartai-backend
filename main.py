# Standard library imports
import os
if os.environ.get("RENDER") != "true":
    from dotenv import load_dotenv
    load_dotenv()
import io
import json
import uuid
import logging
import shutil
import subprocess
from zipfile import ZipFile
from datetime import datetime
from typing import Dict, List, Any

# ─────────────────────────────────────────────
# Third-party imports
import aiofiles
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from starlette.responses import FileResponse, HTMLResponse
from fastapi import (
    FastAPI, UploadFile, File, Depends,
    HTTPException, Header, Request, Body, Form
)
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from alembic.config import Config
from alembic import command

# ─────────────────────────────────────────────s
# Local app imports
from config import settings
# FIX: Only import Base and SessionLocal from the new, simple database.py
from database import Base, SessionLocal
from auth import (
    get_current_user,
    create_password_reset_token,
    verify_password_reset_token,
    get_password_hash
)
from email_utils import send_email
# FIX: Import the router from `auth_routes.py` NOT `auth.py`
from auth_routes import router as auth_router
from models import UserFile, User
from qa_handler import router as qa_router
from transcription_routes import router as transcription_router
from upload_processor import transcribe_audio

if not settings.database_url:
    raise ValueError(
        "FATAL: DATABASE_URL is not set. Application cannot start.")

# ===============================================
# DATABASE SETUP - The Single Source of Truth
# ===============================================
engine = create_engine(settings.database_url)
SessionLocal.configure(bind=engine)

# Bind the engine to the SessionLocal class we imported from database.py
SessionLocal.configure(bind=engine)

# FIX: The get_db dependency is now defined HERE, in main.py


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """A helper function to create DB tables."""
    Base.metadata.create_all(bind=engine)


# initialize the app
app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://smartai-pg.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ensure folders exist on startup
os.makedirs("segments", exist_ok=True)
os.makedirs(settings.transcript_dir, exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# then mount static files
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")


# register routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(transcription_router,
                   prefix="/transcription", tags=["transcription"])
app.include_router(qa_router, prefix="/qa", tags=["qa"])


@app.on_event("startup")
async def startup_event():
    print("Application startup: Creating database tables if they don't exist...")
    create_tables()
    print("Database tables check complete.")
    logging.info("Database tables created if not existing.")

# OpenAI client
client = OpenAI(api_key=settings.openai_api_key)

# root route


@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


@app.get("/audio/{filename:path}")
async def serve_audio(filename: str):
    filepath = os.path.join("uploads", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(filepath, media_type="audio/mpeg")


@app.get("/api/transcripts", response_model=List[Dict[str, Any]])
async def get_transcript_list(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    files = db.query(UserFile).filter(UserFile.email == user.email).order_by(
        UserFile.upload_timestamp.desc()
    ).all()
    return [
        {
            "filename": f.filename,
            "file_size": f.file_size,
            "upload_timestamp": f.upload_timestamp,
            "tag": f.tag or ""
        } for f in files
    ]


@app.get("/api/history")
async def api_history(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return await get_transcript_list(user, db)


@app.get("/api/transcript/{filename:path}")
def get_transcript(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    transcript_path = os.path.join(settings.transcript_dir, f"{filename}.txt")
    segments_path = os.path.join(settings.transcript_dir, f"{filename}.json")

    if not os.path.exists(transcript_path):
        raise HTTPException(status_code=404, detail="Transcript not found.")

    with open(transcript_path, "r", encoding="utf-8") as f:
        text = f.read()

    segments = []
    if os.path.exists(segments_path):
        try:
            with open(segments_path, "r", encoding="utf-8") as sf:
                segments = json.load(sf)
        except Exception:
            print(f"Warning: Failed to parse {segments_path}")

    return JSONResponse(content={"transcript": text, "segments": segments})


@app.post("/api/transcript/{filename:path}/segments")
async def save_segments(filename: str, segments_data: dict, user=Depends(get_current_user)):
    try:
        segments_path = os.path.join(
            settings.transcript_dir, f"{filename}.json")
        with open(segments_path, "w", encoding="utf-8") as f:
            json.dump(segments_data["segments"], f, indent=2)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save segments: {str(e)}")


@app.get("/api/share/{filename:path}")
async def get_shared_transcript(filename: str) -> Dict[str, str]:
    safe_filename = os.path.basename(filename)
    path = os.path.join(settings.transcript_dir, f"{safe_filename}.txt")

    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Transcript not found")

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        return {"transcript": content}
    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to read transcript")


@app.get("/api/download/all")
async def download_all_transcripts(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    memory_file = io.BytesIO()
    user_files = db.query(UserFile).filter(UserFile.email == user.email).all()

    with ZipFile(memory_file, 'w') as zipf:
        for file in user_files:
            transcript_path = os.path.join(
                settings.transcript_dir, file.filename + ".txt")
            if os.path.exists(transcript_path):
                zipf.write(transcript_path, arcname=f"{file.filename}.txt")

    memory_file.seek(0)
    headers = {
        "Content-Disposition": f"attachment; filename={user.email}_transcripts.zip"
    }
    return StreamingResponse(memory_file, media_type="application/zip", headers=headers)


@app.get("/api/download/{file_id}")
def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    file_record = db.query(UserFile).filter(
        UserFile.id == file_id, UserFile.user_id == user.id
    ).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path=os.path.join("uploads", file_record.filename), filename=file_record.filename)


@app.get("/segments/{segment_name}")
def serve_segment(segment_name: str):
    segment_path = os.path.join("segments", segment_name)
    if not os.path.exists(segment_path):
        raise HTTPException(status_code=404, detail="Segment not found")
    return FileResponse(segment_path)


class SegmentInput(BaseModel):
    segment_text: str
    filename: str | None = None
    timestamp: float | None = None


@app.post("/api/quiz/generate")
def generate_question(
    input_data: SegmentInput,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        prompt = f"""
You are a training assistant. Read the following transcript segment and generate a clear, concise question that tests the user's understanding of the content. Be specific but brief.

Segment:
{input_data.segment_text.strip()}

Question:
"""
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a training assistant that helps quiz users on transcripts."},
                {"role": "user", "content": prompt.strip()}
            ]
        )
        question = completion.choices[0].message.content.strip()

        if input_data.filename and input_data.timestamp is not None:
            quiz_path = os.path.join(
                settings.transcript_dir, f"{input_data.filename}_quiz.json")
            quiz_entry = {
                "segment": input_data.segment_text.strip(),
                "question": question,
                "timestamp": input_data.timestamp
            }

            existing = []
            if os.path.exists(quiz_path):
                with open(quiz_path, "r", encoding="utf-8") as f:
                    try:
                        existing = json.load(f)
                    except Exception:
                        print(f"Warning: Could not parse existing quiz file.")
            existing.append(quiz_entry)
            with open(quiz_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)

        return {"question": question}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/quiz/{filename:path}")
def get_saved_quiz(filename: str, user=Depends(get_current_user)):
    quiz_path = os.path.join(settings.transcript_dir, f"{filename}_quiz.json")

    if not os.path.exists(quiz_path):
        return {"quiz": []}

    try:
        with open(quiz_path, "r", encoding="utf-8") as f:
            quiz_data = json.load(f)
            return {"quiz": quiz_data}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to load quiz")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Server error: {str(exc)}"}
    )

# -----------------------------------------------------------
# NEW, UNIFIED PASSWORD RESET FLOW
# -----------------------------------------------------------


class EmailSchema(BaseModel):
    email: EmailStr


@app.post("/request-password-reset")
async def request_password_reset(body: EmailSchema, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        # Don't reveal if a user exists for security reasons.
        # Always return a success-like message.
        return JSONResponse(status_code=200, content={"message": "If an account with that email exists, a password reset link has been sent."})

    token = create_password_reset_token(email=user.email)
    # This creates a full, clickable URL like https://yourapp.onrender.com/reset-password/the-token
    reset_url = str(request.url_for('reset_password_form', token=token))

    html_body = f"""
    <p>Hi {user.name or 'there'},</p>
    <p>You requested a password reset for your SmartAI Transcriber account. Please click the link below to set a new password:</p>
    <p><a href="{reset_url}">{reset_url}</a></p>
    <p>This link is valid for 15 minutes.</p>
    <p>If you did not request this, please ignore this email and your password will remain unchanged.</p>
    """

    await send_email(
        recipients=[user.email],
        subject="Your SmartAI Password Reset Link",
        body=html_body
    )

    return JSONResponse(status_code=200, content={"message": "If an account with that email exists, a password reset link has been sent."})


@app.get("/reset-password/{token}", name="reset_password_form", response_class=HTMLResponse)
async def reset_password_form(token: str):
    # This route just serves the static HTML form we created.
    # The token in the URL will be handled by the form's JavaScript.
    return FileResponse("static/reset_password_form.html")


class ResetPasswordPayload(BaseModel):
    new_password: str


@app.post("/reset-password/{token}")
async def reset_password_handler(token: str, payload: ResetPasswordPayload, db: Session = Depends(get_db)):
    email = verify_password_reset_token(token)
    if not email:
        raise HTTPException(
            status_code=400, detail="Invalid or expired token. Please request a new reset link.")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        # This case is unlikely if the token is valid, but good for security.
        raise HTTPException(status_code=404, detail="User not found.")

    user.hashed_password = get_password_hash(payload.new_password)
    db.commit()

    return {"message": "Password has been reset successfully."}


@app.post("/run-migrations")
def run_migrations():
    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        return {"status": "success", "message": "Migrations applied."}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Migration failed: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
