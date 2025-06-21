from transcription_routes import router as transcription_router
from passlib.context import CryptContext
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel  # Keep this for regular Pydantic models
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi import FastAPI, UploadFile, Depends, HTTPException
from datetime import datetime
import json
import traceback
import subprocess
import shutil
import os
from database import engine, get_db, SessionLocal
from models import Base, ActivityLog, UserFile, QAHistory
from upload_processor import transcribe_audio, get_openai_client
from pinecone_sdk import search_similar_chunks
from auth import get_current_user, authenticate_user, register_user, create_access_token
from auth import verify_token
from email_utils import send_email_with_attachment
from config import settings  # Import the settings instance from config.py
from qa_handler import router as qa_router
from dotenv import load_dotenv
load_dotenv()  # Load environment variables first

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pydantic models (these use BaseModel, not BaseSettings)


class AskRequest(BaseModel):
    question: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ResetPasswordRequest(BaseModel):
    email: str
    password: str
    code: str


# Now use settings from config.py
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.transcript_dir, exist_ok=True)
os.makedirs(settings.static_dir, exist_ok=True)

# FastAPI app initialization
app = FastAPI(title="SmartAI Transcription Service", version="2.0.0")

# Initialize database
Base.metadata.create_all(bind=engine)

# Mount static files
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(qa_router)
app.include_router(transcription_router)

# Utility functions


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def log_activity(email: str, action: str, filename: str = None, db: Session = None):
    """Log user activity to database and file."""
    if db is None:
        return

    timestamp = datetime.utcnow()

    # Log to database
    new_entry = ActivityLog(
        email=email,
        action=action,
        filename=filename,
        timestamp=timestamp.isoformat()
    )
    db.add(new_entry)
    db.commit()

    # Log to file (optional backup)
    try:
        with open(settings.activity_log_path, "a") as f:
            f.write(
                f"{timestamp.isoformat()}|{email}|{action}|{filename or ''}\n")
    except Exception as e:
        print(f"Warning: Failed to write to activity log file: {e}")

# Routes


@app.get("/")
def read_root():
    """Serve the main application page."""
    return FileResponse("static/index.html")


@app.get("/api/history")
async def list_transcripts(user=Depends(get_current_user), db: Session = Depends(get_db)):
    files = db.query(UserFile).filter(UserFile.email == user.email).all()
    return {"files": [{"filename": f.filename, "tag": f.tag} for f in files]}


@app.post("/register")
def register(payload: LoginRequest, db: Session = Depends(get_db)):
    """Register a new user."""
    try:
        # Hash the password before storing
        hashed_password = hash_password(payload.password)
        register_user(db, payload.email, hashed_password)
        log_activity(payload.email, "USER_REGISTERED", db=db)
        return {"message": "User registered successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return access token."""
    try:
        user = authenticate_user(db, payload.email, payload.password)
        token = create_access_token(data={"sub": user.email})
        log_activity(payload.email, "USER_LOGIN", db=db)
        return {"access_token": token, "token_type": "bearer"}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/upload-and-transcribe")
async def upload_and_transcribe(file: UploadFile, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Upload a file and transcribe it."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    try:
        # Sanitize filename
        filename = os.path.basename(file.filename)
        upload_path = os.path.join(settings.upload_dir, filename)

        # Save uploaded file
        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        ext = os.path.splitext(filename)[1].lower()
        audio_path = upload_path

        # Convert video files to audio
        if ext in [".mp4", ".mov", ".mkv", ".avi"]:
            audio_path = upload_path.rsplit(".", 1)[0] + "_converted.wav"
            subprocess.run([
                "ffmpeg", "-y", "-i", upload_path, "-vn",
                "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path
            ], check=True, capture_output=True, text=True)
        elif ext not in settings.allowed_extensions:
            raise HTTPException(
                status_code=400, detail=f"Unsupported file format: {ext}")

        # Transcribe audio
        transcript = transcribe_audio(audio_path)

        # Save transcript
        txt_path = os.path.join(settings.transcript_dir, filename + ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript)

        # Generate summary
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

        # Log activity
        log_activity(user.email, "FILE_TRANSCRIBED", filename, db=db)

        return {
            "filename": filename,
            "transcript": transcript,
            "summary": summary
        }

    except subprocess.CalledProcessError as e:
        error_msg = f"FFmpeg error: {e.stderr if e.stderr else 'Unknown error'}"
        raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Error during upload: {str(e)}")
    finally:
        # Clean up temporary files
        try:
            if os.path.exists(upload_path):
                os.remove(upload_path)
            if audio_path != upload_path and os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception as e:
            print(f"Warning: Failed to clean up temporary files: {e}")


@app.post("/ask")
async def ask_question(request: AskRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Ask a question about the transcribed content."""
    question = request.question

    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        # Search for relevant chunks
        chunks = search_similar_chunks(question, top_k=5)
        context = "\n\n".join([c["text"] for c in chunks])

        # Create prompt
        prompt = f"""You are a helpful assistant. Use the following transcript snippets to answer the question.

Context:
{context}

Question: {question}

Please provide a helpful and accurate answer based on the context provided."""

        # Get streaming response from OpenAI
        client = get_openai_client()
        stream = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.3,
            stream=True
        )

        answer_accumulator = []

        def event_generator():
            """Generate server-sent events for streaming response."""
            # Send sources first
            yield f"data: {json.dumps({'type': 'sources', 'data': chunks})}\n\n"

            # Stream the answer
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    answer_accumulator.append(token)
                    yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

            # Send end signal
            yield f"data: {json.dumps({'type': 'end'})}\n\n"

        def save_history():
            """Save Q&A history to database."""
            try:
                from models import QAHist
                db_session = SessionLocal()
                db_session.add(QAHist(
                    email=user.email,
                    question=question,
                    answer="".join(answer_accumulator).strip(),
                    timestamp=datetime.utcnow()
                ))
                db_session.commit()
                db_session.close()

                # Log activity
                log_activity(user.email, "QUESTION_ASKED", db=db)
            except Exception as e:
                print(f"Error saving Q&A history: {e}")

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            background=BackgroundTask(save_history)
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Error processing question: {str(e)}")


@app.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset user password with verification code."""
    # Verify reset code
    if payload.code != "smartai2024":  # Consider using a more secure system
        raise HTTPException(status_code=401, detail="Invalid reset code")

    # Find user
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # Hash new password and update
        user.password = hash_password(payload.password)
        db.commit()

        # Log activity
        log_activity(payload.email, "PASSWORD_RESET", db=db)

        return {"message": "Password updated successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to update password")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
