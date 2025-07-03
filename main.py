# Standard library imports
import os
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
from starlette.responses import FileResponse
from fastapi import (
    FastAPI, APIRouter, UploadFile, File, Depends,
    HTTPException, Header, Request, Body
)
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from alembic.config import Config
from alembic import command
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# Local app imports
from config import Settings
from database import get_db, create_tables
from auth import get_current_user
from auth_routes import router as auth_router
from models import UserFile, User
from qa_handler import router as qa_router
from transcription_routes import router as transcription_router
from upload_processor import transcribe_audio

# load .env into local dev (Render will inject separately)
load_dotenv()

# create the settings **at runtime**
settings = Settings()

# initialize the app
app = FastAPI()

app.include_router(transcription_router)
app.include_router(qa_router)
app.include_router(auth_router)


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# CORS (allow all for dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # dev
        "https://smartai-pg.onrender.com",  # production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SegmentInput(BaseModel):
    segment_text: str
    filename: str | None = None
    timestamp: float | None = None


# Ensure upload and transcripts directories exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("transcripts", exist_ok=True)
os.makedirs("segments", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/transcripts", StaticFiles(directory="transcripts"),
          name="transcripts")

# Register your routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(transcription_router,
                   prefix="/transcription", tags=["transcription"])
app.include_router(qa_router, prefix="/qa", tags=["qa"])


@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


@app.get("/audio/{filename:path}")
async def serve_audio(filename: str):
    filepath = os.path.join("uploads", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(filepath, media_type="audio/mpeg")


# CHANGE: Changed @router.get to @app.get
@app.get("/api/transcripts")
async def get_transcript_list(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, List[Dict[str, Any]]]:
    files = db.query(UserFile).filter(UserFile.email == user.email).order_by(
        UserFile.upload_timestamp.desc()
    ).all()
    return {
        "files": [
            {
                "filename": f.filename,
                "file_size": f.file_size,
                "upload_timestamp": f.upload_timestamp
            } for f in files
        ]
    }


# CHANGE: Changed @router.get to @app.get
@app.get("/api/history")
async def api_history(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return await get_transcript_list(user, db)


# CHANGE: Changed @router.get to @app.get
@app.get("/api/transcript/{filename:path}")
def get_transcript(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    transcript_path = os.path.join(settings.transcript_dir, filename)
    segments_path = transcript_path.replace(".txt", ".json")

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


# CHANGE: Changed @router.post to @app.post
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


# CHANGE: Changed @router.get to @app.get
@app.get("/api/share/{filename:path}", response_model=None)
async def get_shared_transcript(filename: str) -> Dict[str, str]:
    safe_filename = os.path.basename(filename)
    path = os.path.join(settings.transcript_dir, safe_filename)

    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Transcript not found")

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        return {"transcript": content}
    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to read transcript")


# CHANGE: Changed @router.get to @app.get
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

# Download a file


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

# Serve segments


@app.get("/segments/{segment_name}")
def serve_segment(segment_name: str):
    segment_path = os.path.join("segments", segment_name)
    if not os.path.exists(segment_path):
        raise HTTPException(status_code=404, detail="Segment not found")
    return FileResponse(segment_path)


# CHANGE: Changed @router.post to @app.post
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


# CHANGE: Changed @router.get to @app.get
@app.get("/api/quiz/{filename:path}")
def get_saved_quiz(filename: str, user=Depends(get_current_user)):
    quiz_path = os.path.join(settings.transcript_dir, f"{filename}_quiz.json")

    if not os.path.exists(quiz_path):
        return {"quiz": []}

    try:
        with open(quiz_path, "r", encoding="utf-8") as f:
            quiz_data = json.load(f)
            return {"quiz": quiz_data}
    except Exception as e:
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

if __name__ == "__main__":
    import uvicorn
    import os

    # Use 10000 locally if PORT is not set
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)


@app.post("/reset-password")
def reset_password(data: dict = Body(...)):
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email required")

    # (You can simulate or implement email sending here)
    print(f"Reset link sent to: {email}")

    return {"message": "Reset instructions sent"}

# Alembic migration trigger (optional, for one-click migration)


@app.post("/run-migrations")
def run_migrations():
    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        return {"status": "success", "message": "Migrations applied."}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Migration failed: {e}")
