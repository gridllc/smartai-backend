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
from botocore.exceptions import ClientError  # <-- For better S3 error handling

# Local
from upload_processor import transcribe_audio
from auth import get_current_user
from database import get_db
from config import settings
from models import UserFile, User

router = APIRouter()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# --- Reusable S3 client for all routes ---
s3 = boto3.client("s3", region_name=settings.aws_region)


class SegmentInput(BaseModel):
    segment_text: str
    filename: str | None = None
    timestamp: float | None = None


class NoteInput(BaseModel):
    note: str

# --- New model for tags ---


class TagInput(BaseModel):
    tag: str


class EditQuizInput(BaseModel):
    timestamp: float
    new_question: str


# This route is correct from the previous fix
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

        transcript_text, segments, audio_url, transcript_url, _ = await transcribe_audio(upload_path, unique_name)

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

# This route is correct


@router.get("/api/transcript/{filename:path}")
def get_transcript_from_s3(filename: str, current_user: User = Depends(get_current_user)):
    base_name = os.path.splitext(filename)[0]

    try:
        transcript_key = f"transcripts/{base_name}.txt"
        txt_obj = s3.get_object(Bucket=settings.s3_bucket, Key=transcript_key)
        text = txt_obj["Body"].read().decode("utf-8")
    except ClientError:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    segments = []
    try:
        segments_key = f"transcripts/{base_name}.json"
        seg_obj = s3.get_object(Bucket=settings.s3_bucket, Key=segments_key)
        segments = json.loads(seg_obj["Body"].read().decode("utf-8"))
    except ClientError as e:
        if e.response['Error']['Code'] != 'NoSuchKey':
            print(f"Could not load segments for {filename}: {e}")

    return JSONResponse(content={"transcript": text, "segments": segments})

# --- MODIFIED: Downloads transcripts from S3 ---


@router.get("/api/download/all")
async def download_all_transcripts(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    memory_file = io.BytesIO()
    user_files = db.query(UserFile).filter(UserFile.email == user.email).all()

    with ZipFile(memory_file, 'w') as zipf:
        for file in user_files:
            base_name = os.path.splitext(file.filename)[0]
            transcript_s3_key = f"transcripts/{base_name}.txt"
            arcname = f"{base_name}.txt"
            try:
                obj = s3.get_object(
                    Bucket=settings.s3_bucket, Key=transcript_s3_key)
                transcript_content = obj['Body'].read()
                zipf.writestr(arcname, transcript_content)
            except ClientError:
                print(f"Skipping {transcript_s3_key}, not found in S3.")
                continue

    memory_file.seek(0)
    return StreamingResponse(
        memory_file,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={user.email}_transcripts.zip"}
    )

# --- MODIFIED: Reads/writes quiz data from/to S3 ---


@router.post("/api/quiz/generate")
def generate_question(
    input_data: SegmentInput,
    user=Depends(get_current_user)
):
    prompt = f"""You are a training assistant...Segment:\n{input_data.segment_text.strip()}\n\nQuestion:"""
    completion = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt.strip()}]
    )
    question = completion.choices[0].message.content.strip()

    if input_data.filename:
        base_name = os.path.splitext(input_data.filename)[0]
        s3_key = f"transcripts/{base_name}_quiz.json"
        quiz_entry = {
            "segment": input_data.segment_text.strip(),
            "question": question,
            "timestamp": input_data.timestamp
        }

        existing_quiz = []
        try:
            quiz_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
            existing_quiz = json.load(quiz_obj["Body"])
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchKey':
                raise HTTPException(500, "Failed to check for existing quiz.")

        existing_quiz.append(quiz_entry)
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=json.dumps(existing_quiz, indent=2),
            ContentType="application/json"
        )

    return {"question": question}

# --- MODIFIED: Gets saved quiz from S3 ---


@router.get("/api/quiz/{filename:path}")
def get_saved_quiz(filename: str, user=Depends(get_current_user)):
    base_name = os.path.splitext(filename)[0]
    s3_key = f"transcripts/{base_name}_quiz.json"
    try:
        quiz_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        quiz_data = json.load(quiz_obj["Body"])
        return {"quiz": quiz_data}
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return {"quiz": []}
        raise HTTPException(
            status_code=500, detail="Failed to load quiz from S3")

# --- MODIFIED: Saves note to S3 ---


@router.post("/api/transcript/{filename:path}/note")
def save_note(
    filename: str,
    input_data: NoteInput,
    user=Depends(get_current_user)
):
    base_name = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base_name}_note.json"
    payload = {"email": user.email, "note": input_data.note}
    try:
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=json.dumps(payload).encode("utf-8"),
            ContentType="application/json"
        )
        return {"message": "Note saved successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save note to S3: {str(e)}")

# --- MODIFIED: Gets note from S3 ---


@router.get("/api/transcript/{filename:path}/note")
def get_note(
    filename: str,
    user=Depends(get_current_user)
):
    base_name = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base_name}_note.json"
    try:
        note_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        data = json.loads(note_obj["Body"].read().decode("utf-8"))
        if data.get("email") != user.email:
            raise HTTPException(403, "Unauthorized to access this note")
        return {"note": data.get("note", "")}
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return {"note": ""}
        raise HTTPException(500, "Failed to read note from S3")

# --- NEW: Routes for saving and getting tags from S3 ---


@router.post("/api/transcript/{filename:path}/tag")
def save_tag(filename: str, input_data: TagInput, user=Depends(get_current_user)):
    base_name = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base_name}_tag.json"
    payload = {"email": user.email, "tag": input_data.tag}
    try:
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=json.dumps(payload).encode("utf-8"),
            ContentType="application/json"
        )
        return {"message": "Tag saved successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save tag: {str(e)}")


@router.get("/api/transcript/{filename:path}/tag")
def get_tag(filename: str, user=Depends(get_current_user)):
    base_name = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base_name}_tag.json"
    try:
        tag_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        data = json.loads(tag_obj["Body"].read().decode("utf-8"))
        if data.get("email") != user.email:
            raise HTTPException(403, "Unauthorized")
        return {"tag": data.get("tag", "")}
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return {"tag": ""}
        raise HTTPException(500, "Failed to read tag")

# --- MODIFIED: Deletes all associated files from S3 ---


@router.delete("/api/delete/{filename:path}")
async def delete_transcript(filename: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    safe_name = os.path.basename(filename)
    base = os.path.splitext(safe_name)[0]

    # Delete from DB first
    db_obj = db.query(UserFile).filter(
        UserFile.filename == safe_name,
        UserFile.email == user.email
    ).first()

    if not db_obj:
        raise HTTPException(
            status_code=404, detail="File record not found in database.")

    db.delete(db_obj)
    db.commit()

    # Batch delete all associated files from S3
    keys_to_delete = [
        f"uploads/{safe_name}",
        f"transcripts/{base}.txt",
        f"transcripts/{base}.json",
        f"transcripts/{base}_note.json",
        f"transcripts/{base}_quiz.json",
        f"transcripts/{base}_tag.json"
    ]
    objects_to_delete = [{'Key': key} for key in keys_to_delete]

    try:
        s3.delete_objects(
            Bucket=settings.s3_bucket,
            Delete={'Objects': objects_to_delete, 'Quiet': True}
        )
        return {"message": f"Successfully deleted {safe_name} and all associated data."}
    except Exception as e:
        # The DB entry is already deleted, so we just log the S3 error
        print(f"Error deleting files from S3 for {safe_name}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to delete all files from S3, but DB record was removed.")

# ... (Other routes like suggest, save_segments, quiz updates would follow a similar pattern of using the `s3` client)
a