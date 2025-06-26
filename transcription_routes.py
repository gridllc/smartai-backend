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

        # Save uploaded file locally
        async with aiofiles.open(upload_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)

        # ------------------- THIS IS THE FIX -------------------
        # Unpack all 5 values returned by transcribe_audio.
        # We use `_` to ignore the last value (local transcript_path), which isn't needed here.
        transcript_text, segments, audio_url, transcript_url, _ = await transcribe_audio(upload_path, unique_name)
        # --------------------------------------------------------

        # The segments JSON is now created and uploaded by transcribe_audio,
        # so the redundant code that was here can be removed.

        # Save metadata to DB
        new_file = UserFile(
            email=user.email,
            filename=unique_name,
            file_size=len(content),
            upload_timestamp=datetime.utcnow(),
            audio_url=audio_url,
            transcript_url=transcript_url
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)

        return JSONResponse(status_code=200, content={
            "message": "File uploaded and transcribed",
            "filename": unique_name,
            "audio_url": audio_url,
            "transcript_url": transcript_url
        })

    except Exception:
        import traceback
        print("❌ Upload failed:\n", traceback.format_exc())
        raise HTTPException(
            status_code=500, detail="Upload failed. Check logs for details.")


@router.get("/api/transcript/{filename:path}")
def get_transcript_from_s3(filename: str, current_user: User = Depends(get_current_user)):
    import boto3

    s3 = boto3.client("s3", region_name=settings.aws_region)
    base_name = os.path.splitext(filename)[0]

    try:
        # Construct the correct key for the transcript .txt file
        transcript_key = f"transcripts/{base_name}.txt"
        txt_obj = s3.get_object(Bucket=settings.s3_bucket,
                                Key=transcript_key)
        text = txt_obj["Body"].read().decode("utf-8")
    except Exception:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    # Construct the correct key for the segments .json file
    segments_key = f"transcripts/{base_name}.json"

    try:
        seg_obj = s3.get_object(Bucket=settings.s3_bucket, Key=segments_key)
        segments = json.loads(seg_obj["Body"].read().decode("utf-8"))
    except Exception:
        # If segments file doesn't exist, return an empty list as before
        segments = []

    return JSONResponse(content={"transcript": text, "segments": segments})


@router.get("/api/share/{filename:path}", response_model=None)
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
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/api/quiz/{filename:path}")
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


@router.post("/api/transcript/{filename:path}/note")
def save_note(filename: str, note_data: dict, user=Depends(get_current_user)):
    base = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base}_note.json"
    payload = {
        "email": user.email,
        "note": note_data.get("note", "")
    }

    try:
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=json.dumps(payload).encode("utf-8"),
            ContentType="application/json"
        )
        return {"message": "Note saved"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to save note")

@router.get("/api/transcript/{filename:path}/note")
def get_note(filename: str, user=Depends(get_current_user)):
    base = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base}_note.json"

    try:
        note_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        data = json.loads(note_obj["Body"].read().decode("utf-8"))
        if data["email"] != user.email:
            raise HTTPException(status_code=403, detail="Unauthorized")
        return {"note": data["note"]}
    except s3.exceptions.NoSuchKey:
        return {"note": ""}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to load note")


@router.post("/api/transcript/{filename:path}/segments")
async def save_segments(filename: str, data: dict, user=Depends(get_current_user)):
    safe_filename = os.path.basename(filename)
    base_name = os.path.splitext(safe_filename)[0]
    s3_key = f"transcripts/{base_name}.json"
    segments_content = json.dumps(data.get("segments", []), indent=2)

    try:
        s3 = boto3.client("s3", region_name=settings.aws_region)
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=segments_content.encode("utf-8"),
            ContentType="application/json"
        )
        return {"message": "Segments updated successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save segments to S3: {str(e)}"
        )


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


@router.post("/api/transcript/{filename:path}/auto-segment")
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


@router.delete("/api/quiz/{filename:path}/{timestamp}")
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


@router.patch("/api/quiz/{filename:path}")
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


@router.delete("/api/delete/{filename:path}")
async def delete_transcript(filename: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    from s3_utils import s3
    import traceback

    safe_name = os.path.basename(filename)
    base = os.path.splitext(safe_name)[0]

    try:
        # Delete from S3
        s3.delete_object(Bucket=settings.s3_bucket, Key=f"uploads/{safe_name}")
        s3.delete_object(Bucket=settings.s3_bucket,
                         Key=f"transcripts/{base}.txt")
        s3.delete_object(Bucket=settings.s3_bucket,
                         Key=f"transcripts/{base}.json")

        # Delete from DB
        db_obj = db.query(UserFile).filter(
            UserFile.filename == safe_name,
            UserFile.email == user.email
        ).first()

        if db_obj:
            db.delete(db_obj)
            db.commit()

        return {"message": f"{safe_name} deleted from S3 and DB."}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Failed to delete file: {str(e)}")
