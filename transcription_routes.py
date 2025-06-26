# Standard Library
import os
import io
import json
import uuid
from datetime import datetime
from zipfile import ZipFile

# Third-Party
import boto3
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
from typing import Dict, List, Any

# Local
from upload_processor import transcribe_audio
from auth import get_current_user
from database import get_db
from config import settings
from models import UserFile, User

router = APIRouter()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class SegmentInput(BaseModel):
    segment_text: str
    filename: str | None = None
    timestamp: float | None = None


class NoteInput(BaseModel):
    note: str


class EditQuizInput(BaseModel):
    timestamp: float
    new_question: str


@router.get("/api/transcripts", response_model=None)
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
def get_transcript_from_s3(filename: str, current_user: User = Depends(get_current_user)):
    import boto3

    s3 = boto3.client("s3", region_name=settings.aws_region)

    try:
        txt_obj = s3.get_object(Bucket=settings.s3_bucket,
                                Key=f"transcripts/{filename}")
        text = txt_obj["Body"].read().decode("utf-8")
    except Exception:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    segments_key = f"transcripts/{filename.replace('.txt', '.json')}"
    try:
        seg_obj = s3.get_object(Bucket=settings.s3_bucket, Key=segments_key)
        segments = json.loads(seg_obj["Body"].read().decode("utf-8"))
    except Exception:
        segments = []

    return JSONResponse(content={"transcript": text, "segments": segments})

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

        # ✅ Validate and save question if filename + timestamp exist
        if input_data.filename:
            if input_data.timestamp is None or not isinstance(input_data.timestamp, (float, int)):
                raise HTTPException(
                    status_code=400, detail="Missing or invalid timestamp")

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
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to load quiz")


@router.post("/api/transcript/{filename}/note")
def save_note(
    filename: str,
    input: NoteInput,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    safe_name = os.path.basename(filename)
    note_path = os.path.join(settings.transcript_dir, f"{safe_name}_note.json")

    try:
        with open(note_path, "w", encoding="utf-8") as f:
            json.dump({"email": user.email, "note": input.note}, f)
        return {"message": "Note saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save note")


@router.get("/api/transcript/{filename}/note")
def get_note(
    filename: str,
    user=Depends(get_current_user)
):
    safe_name = os.path.basename(filename)
    note_path = os.path.join(settings.transcript_dir, f"{safe_name}_note.json")

    if not os.path.exists(note_path):
        return {"note": ""}

    try:
        with open(note_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data["email"] != user.email:
            raise HTTPException(
                status_code=403, detail="Unauthorized to access this note")
        return {"note": data["note"]}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read note")


@router.post("/api/transcript/{filename}/segments")
async def save_segments(filename: str, data: dict, user=Depends(get_current_user)):
    safe_filename = os.path.basename(filename)
    path = os.path.join(settings.transcript_dir,
                        safe_filename.replace(".txt", ".json"))

    try:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data.get("segments", []), indent=2))
        return {"message": "Segments updated successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save segments: {str(e)}")


@router.post("/api/suggest")
def suggest_text(data: dict, user=Depends(get_current_user)):
    try:
        prompt = f"Improve the clarity and professionalism of the following text:\n\n\"{data['text']}\"\n\nImproved:"
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an assistant that rewords transcript segments for clarity."},
                {"role": "user", "content": prompt}
            ]
        )
        suggestion = completion.choices[0].message.content.strip()
        return {"suggestion": suggestion}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Suggestion failed: {str(e)}")


@router.post("/api/transcript/{filename}/auto-segment")
def auto_segment_transcript(filename: str, user=Depends(get_current_user)):
    transcript_path = os.path.join(settings.transcript_dir, filename)
    segment_path = transcript_path.replace(".txt", ".json")

    if not os.path.exists(transcript_path):
        raise HTTPException(
            status_code=404, detail="Transcript file not found.")

    with open(transcript_path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    prompt = f"""Break this transcript into segments. Each segment should be a short paragraph with an estimated start time in seconds.
Return JSON as a list of objects with 'start', 'end', and 'text'. Use even spacing if no timestamps exist.

Transcript:
{text[:4000]}"""  # truncate if needed

    try:
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a transcript segmentation assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        segments = json.loads(completion.choices[0].message.content.strip())

        with open(segment_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=2)

        return {"message": "Segments generated", "count": len(segments)}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Segmentation failed: {str(e)}")


@router.delete("/api/quiz/{filename}/{timestamp}")
def delete_quiz_question(filename: str, timestamp: float, user=Depends(get_current_user)):
    safe_name = os.path.basename(filename)
    path = os.path.join(settings.transcript_dir, f"{safe_name}_quiz.json")

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Quiz file not found")

    try:
        with open(path, "r", encoding="utf-8") as f:
            quiz_data = json.load(f)

        new_data = [q for q in quiz_data if abs(
            q.get("timestamp", -1) - timestamp) > 0.01]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2)

        return {"message": "Question deleted"}
    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to delete question")


@router.patch("/api/quiz/{filename}")
def update_quiz_question(filename: str, update: EditQuizInput, user=Depends(get_current_user)):
    safe_name = os.path.basename(filename)
    path = os.path.join(settings.transcript_dir, f"{safe_name}_quiz.json")

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Quiz file not found")

    try:
        with open(path, "r", encoding="utf-8") as f:
            quiz_data = json.load(f)

        updated = False
        for q in quiz_data:
            if abs(q.get("timestamp", -1) - update.timestamp) < 0.01:
                q["question"] = update.new_question
                updated = True
                break

        if not updated:
            raise HTTPException(
                status_code=404, detail="Quiz question not found")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(quiz_data, f, indent=2)

        return {"message": "Quiz updated"}
    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to update question")


@router.delete("/api/quiz/{filename}")
def delete_quiz_question(
    filename: str,
    timestamp: float = Query(...),
    user=Depends(get_current_user)
):
    safe_name = os.path.basename(filename)
    path = os.path.join(settings.transcript_dir, f"{safe_name}_quiz.json")

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Quiz file not found")

    try:
        with open(path, "r", encoding="utf-8") as f:
            quiz_data = json.load(f)

        updated = [q for q in quiz_data if abs(
            q.get("timestamp", -1) - timestamp) >= 0.01]

        if len(updated) == len(quiz_data):
            raise HTTPException(
                status_code=404, detail="Quiz question not found")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2)

        return {"message": "Quiz question deleted"}
    except Exception:
        raise HTTPException(
            status_code=500, detail="Failed to delete question")
