from email_utils import send_email_with_attachment
from qa_handler import router as qa_router
from transcription_routes import router as transcription_router
from typing import Dict, List, Any
from zipfile import ZipFile
import logging
import aiofiles
import json
import io
from email.message import EmailMessage
import smtplib
import subprocess
import shutil
import os
from openai import OpenAI
from config import settings
from database import get_db, create_tables
from auth import get_current_user
from models import UserFile, User
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import FastAPI, APIRouter, UploadFile, File, Depends, HTTPException, Header, Request, Body
from pydantic import BaseModel
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv()


router = APIRouter()


app = FastAPI()


@app.on_event("startup")
def init_db():
    create_tables()


app.include_router(transcription_router)
app.include_router(qa_router)
app.include_router(router)  # This one includes routes from this same file


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# CORS (allow all for dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SegmentInput(BaseModel):
    segment_text: str
    filename: str | None = None
    timestamp: float | None = None


# Ensure the uploads directory exists
# Ensure upload and transcript directories exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("transcripts", exist_ok=True)


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/transcripts", StaticFiles(directory="transcripts"),
          name="transcripts")

# Root route


@app.get("/")
def root():
    return {"message": "SmartAI is running."}

# Serve uploaded audio directly


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    filepath = os.path.join("uploads", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(filepath, media_type="audio/mpeg")


@router.get("/api/transcripts")
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


@router.get("/api/transcript/{filename}")
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


@router.post("/api/transcript/{filename}/segments")
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


@router.get("/api/share/{filename}", response_model=None)
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


@router.get("/api/download/all")
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


@router.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        extension = os.path.splitext(file.filename)[1]
        unique_name = f"{uuid.uuid4().hex}{extension}"
        upload_path = os.path.join("uploads", unique_name)

        async with aiofiles.open(upload_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)

        transcript_text, segments = await transcribe_audio(upload_path, unique_name)
        transcript_path = os.path.join(
            settings.transcript_dir, unique_name + ".txt")
        segments_path = transcript_path.replace(".txt", ".json")

        async with aiofiles.open(transcript_path, "w", encoding="utf-8") as f:
            await f.write(transcript_text)
        async with aiofiles.open(segments_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(segments, indent=2))

        new_file = UserFile(
            email=user.email,
            filename=unique_name,
            file_size=len(content),
            upload_timestamp=datetime.utcnow()
        )
        db.add(new_file)
        db.commit()

        return {"message": "File uploaded and transcribed", "filename": unique_name}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/api/quiz/generate")
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


@router.get("/api/quiz/{filename}")
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
    uvicorn.run("main:app", host="0.0.0.0", port=10000, reload=True)
