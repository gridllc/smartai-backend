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
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI
from typing import Dict, List, Any
from botocore.exceptions import ClientError

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


# --- Pydantic Models ---
class SegmentInput(BaseModel):
    segment_text: str
    filename: str
    timestamp: float


class NoteInput(BaseModel):
    note: str


class TagInput(BaseModel):
    tag: str


class EditQuizInput(BaseModel):
    timestamp: float
    new_question: str


# --- Core File Handling & Management Routes ---

@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        extension = os.path.splitext(file.filename)[1]
        unique_name = f"{uuid.uuid4().hex}{extension}"
        # Create a temporary local path for processing
        local_temp_path = os.path.join("uploads", unique_name)
        os.makedirs("uploads", exist_ok=True)  # Ensure the directory exists

        async with aiofiles.open(local_temp_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)

        # transcribe_audio saves transcript and segments to S3 and returns URLs
        _, _, audio_url, transcript_url, _ = await transcribe_audio(local_temp_path, unique_name)

        # Clean up local temp file after processing
        os.remove(local_temp_path)

        new_file = UserFile(
            filename=unique_name,
            file_size=len(content),
            upload_timestamp=datetime.utcnow(),
            user_id=user.id,                 # correctly link the user
            audio_url=audio_url,
            transcript_url=transcript_url
        )

        db.add(new_file)
        db.commit()
        db.refresh(new_file)

        return JSONResponse(status_code=200, content={
            "message": "File uploaded and transcribed", "filename": unique_name,
            "audio_url": audio_url, "transcript_url": transcript_url
        })
    except Exception:
        import traceback
        print("❌ Upload failed:\n", traceback.format_exc())
        raise HTTPException(
            status_code=500, detail="Upload failed. Check server logs for details.")


@router.get("/api/transcripts", response_model=List[Dict[str, Any]])
async def get_transcript_list(user=Depends(get_current_user), db: Session = Depends(get_db)):
    files = db.query(UserFile).filter(UserFile.user_id == user.id).order_by(
        UserFile.upload_timestamp.desc()).all()

    return [
        {
            "filename": f.filename,
            "file_size": f.file_size,
            "upload_timestamp": f.upload_timestamp.isoformat(),
            "audio_url": f.audio_url,
            "transcript_url": f.transcript_url
        }
        for f in files
    ]


@router.get("/api/transcript/{filename:path}")
def get_transcript_from_s3(filename: str, user=Depends(get_current_user)):
    """Gets the main transcript text and its segments JSON from S3."""
    base_name = os.path.splitext(filename)[0]
    try:
        txt_obj = s3.get_object(Bucket=settings.s3_bucket,
                                Key=f"transcripts/{base_name}.txt")
        text = txt_obj["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            raise HTTPException(
                status_code=404, detail="Transcript text file not found.")
        raise HTTPException(
            status_code=500, detail="S3 error fetching transcript.")

    try:
        seg_obj = s3.get_object(Bucket=settings.s3_bucket,
                                Key=f"transcripts/{base_name}.json")
        segments = json.loads(seg_obj["Body"].read().decode("utf-8"))
    except ClientError:
        segments = []  # It's okay if segments don't exist, return empty list

    return JSONResponse(content={"transcript": text, "segments": segments})


@router.delete("/api/delete/{filename:path}")
async def delete_transcript(filename: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Deletes a file record from DB and all associated files from S3."""
    db_obj = db.query(UserFile).filter(UserFile.filename ==
                                       filename, UserFile.email == user.email).first()
    if not db_obj:
        raise HTTPException(
            status_code=404, detail="File record not found in database.")

    db.delete(db_obj)
    db.commit()

    base = os.path.splitext(filename)[0]
    keys_to_delete = [
        f"uploads/{filename}", f"transcripts/{base}.txt", f"transcripts/{base}.json",
        f"transcripts/{base}_note.json", f"transcripts/{base}_quiz.json", f"transcripts/{base}_tag.json"
    ]
    objects_to_delete = [{'Key': key} for key in keys_to_delete]

    try:
        s3.delete_objects(Bucket=settings.s3_bucket, Delete={
                          'Objects': objects_to_delete, 'Quiet': True})
        return {"message": f"Successfully deleted {filename} and all associated data."}
    except Exception as e:
        print(f"Error deleting files from S3 for {filename}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to delete all files from S3, but DB record was removed.")

# --- Quiz Routes (S3-based) ---


@router.post("/api/quiz/generate")
def generate_question(input_data: SegmentInput, user=Depends(get_current_user)):
    """Generates a quiz question and appends it to the quiz file in S3."""
    try:
        prompt = f"You are a training assistant...Segment:\n{input_data.segment_text.strip()}\n\nQuestion:"
        completion = client.chat.completions.create(
            model="gpt-4", messages=[{"role": "user", "content": prompt}])
        question = completion.choices[0].message.content.strip()

        base_name = os.path.splitext(input_data.filename)[0]
        s3_key = f"transcripts/{base_name}_quiz.json"
        quiz_entry = {"segment": input_data.segment_text.strip(
        ), "question": question, "timestamp": input_data.timestamp}

        try:
            quiz_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
            existing_quiz = json.load(quiz_obj["Body"])
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                existing_quiz = []
            else:
                raise HTTPException(500, "Failed to check for existing quiz.")

        existing_quiz.append(quiz_entry)
        s3.put_object(Bucket=settings.s3_bucket, Key=s3_key, Body=json.dumps(
            existing_quiz, indent=2), ContentType="application/json")
        return {"question": question}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Failed to generate question: {str(e)}")


@router.get("/api/quiz/{filename:path}")
def get_saved_quiz(filename: str, user=Depends(get_current_user)):
    """Gets the entire quiz file from S3."""
    base_name = os.path.splitext(filename)[0]
    s3_key = f"transcripts/{base_name}_quiz.json"
    try:
        quiz_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        return {"quiz": json.load(quiz_obj["Body"])}
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return {"quiz": []}
        raise HTTPException(
            status_code=500, detail="Failed to load quiz from S3")


@router.patch("/api/quiz/{filename:path}")
def update_quiz_question(filename: str, update: EditQuizInput, user=Depends(get_current_user)):
    """Updates a specific quiz question in S3."""
    base_name = os.path.splitext(filename)[0]
    s3_key = f"transcripts/{base_name}_quiz.json"
    try:
        quiz_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        quiz_data = json.load(quiz_obj["Body"])
    except ClientError:
        raise HTTPException(status_code=404, detail="Quiz file not found")

    updated = False
    for q in quiz_data:
        if abs(q.get("timestamp", -1) - update.timestamp) < 0.01:
            q["question"] = update.new_question
            updated = True
            break

    if not updated:
        raise HTTPException(
            status_code=404, detail="Quiz question with that timestamp not found")

    s3.put_object(Bucket=settings.s3_bucket, Key=s3_key, Body=json.dumps(
        quiz_data, indent=2), ContentType="application/json")
    return {"message": "Quiz updated"}


@router.delete("/api/quiz/{filename:path}/{timestamp}")
def delete_quiz_question(filename: str, timestamp: float, user=Depends(get_current_user)):
    """Deletes a specific quiz question from the file in S3."""
    base_name = os.path.splitext(filename)[0]
    s3_key = f"transcripts/{base_name}_quiz.json"
    try:
        quiz_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        quiz_data = json.load(quiz_obj["Body"])
    except ClientError:
        raise HTTPException(status_code=404, detail="Quiz file not found")

    initial_length = len(quiz_data)
    new_data = [q for q in quiz_data if abs(
        q.get("timestamp", -1) - timestamp) > 0.01]

    if len(new_data) == initial_length:
        raise HTTPException(
            status_code=404, detail="Quiz question with that timestamp not found")

    s3.put_object(Bucket=settings.s3_bucket, Key=s3_key, Body=json.dumps(
        new_data, indent=2), ContentType="application/json")
    return {"message": "Question deleted"}


# --- Note and Tag Routes (S3-based) ---

@router.post("/api/transcript/{filename:path}/note")
def save_note(filename: str, input_data: NoteInput, user=Depends(get_current_user)):
    """Saves a note for a transcript to a JSON file in S3."""
    base_name = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base_name}_note.json"
    payload = {"email": user.email, "note": input_data.note}
    s3.put_object(Bucket=settings.s3_bucket, Key=s3_key,
                  Body=json.dumps(payload), ContentType="application/json")
    return {"message": "Note saved successfully"}


@router.get("/api/transcript/{filename:path}/note")
def get_note(filename: str, user=Depends(get_current_user)):
    """Gets a note for a transcript from S3."""
    base_name = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base_name}_note.json"
    try:
        note_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        data = json.load(note_obj["Body"])
        if data.get("email") != user.email:
            raise HTTPException(403, "Unauthorized")
        return {"note": data.get("note", "")}
    except ClientError:
        return {"note": ""}


@router.post("/api/transcript/{filename:path}/tag")
def save_tag(filename: str, input_data: TagInput, user=Depends(get_current_user)):
    """Saves a tag for a transcript to a JSON file in S3."""
    base_name = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base_name}_tag.json"
    payload = {"email": user.email, "tag": input_data.tag}
    s3.put_object(Bucket=settings.s3_bucket, Key=s3_key,
                  Body=json.dumps(payload), ContentType="application/json")
    return {"message": "Tag saved successfully"}


@router.get("/api/transcript/{filename:path}/tag")
def get_tag(filename: str, user=Depends(get_current_user)):
    """Gets a tag for a transcript from S3."""
    base_name = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base_name}_tag.json"
    try:
        tag_obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        data = json.load(tag_obj["Body"])
        if data.get("email") != user.email:
            raise HTTPException(403, "Unauthorized")
        return {"tag": data.get("tag", "")}
    except ClientError:
        return {"tag": ""}

# --- Utility and Other Routes (S3-based) ---


@router.post("/api/transcript/{filename:path}/segments")
async def save_segments(filename: str, data: dict, user=Depends(get_current_user)):
    """Updates the segments JSON file in S3."""
    base_name = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base_name}.json"
    segments_content = json.dumps(data.get("segments", []), indent=2)

    try:
        s3.put_object(
            Bucket=settings.s3_bucket, Key=s3_key,
            Body=segments_content.encode("utf-8"), ContentType="application/json"
        )
        return {"message": "Segments updated successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save segments to S3: {str(e)}")


@router.post("/api/suggest")
def suggest_text(data: dict, user=Depends(get_current_user)):
    """Uses OpenAI to suggest improvements for a piece of text."""
    try:
        prompt = f"Improve the clarity and professionalism of the following text:\n\n\"{data['text']}\"\n\nImproved:"
        completion = client.chat.completions.create(
            model="gpt-4", messages=[{"role": "user", "content": prompt}])
        suggestion = completion.choices[0].message.content.strip()
        return {"suggestion": suggestion}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Suggestion failed: {str(e)}")


@router.post("/api/transcript/{filename:path}/auto-segment")
def auto_segment_transcript(filename: str, user=Depends(get_current_user)):
    """Fetches a transcript from S3, uses OpenAI to segment it, and saves the new segments file to S3."""
    base_name = os.path.splitext(filename)[0]
    transcript_key = f"transcripts/{base_name}.txt"
    segment_key = f"transcripts/{base_name}.json"

    try:
        txt_obj = s3.get_object(Bucket=settings.s3_bucket, Key=transcript_key)
        text = txt_obj["Body"].read().decode("utf-8")
    except ClientError:
        raise HTTPException(
            status_code=404, detail="Transcript file not found in S3.")

    prompt = f"Break this transcript into segments...Transcript:\n{text[:4000]}"
    try:
        completion = client.chat.completions.create(
            model="gpt-4", messages=[{"role": "user", "content": prompt}])
        segments = json.loads(completion.choices[0].message.content.strip())

        s3.put_object(Bucket=settings.s3_bucket, Key=segment_key, Body=json.dumps(
            segments, indent=2), ContentType="application/json")
        return {"message": "Segments generated and saved", "count": len(segments)}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"AI segmentation failed: {str(e)}")


@router.get("/api/share/{filename:path}", response_model=None)
async def get_shared_transcript(filename: str) -> Dict[str, str]:
    """Gets a transcript from S3, intended for a public-facing share link."""
    base_name = os.path.splitext(os.path.basename(filename))[0]
    s3_key = f"transcripts/{base_name}.txt"
    try:
        obj = s3.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        content = obj["Body"].read().decode("utf-8")
        return {"transcript": content}
    except ClientError:
        raise HTTPException(
            status_code=404, detail="Shared transcript not found.")


@router.get("/api/download/all")
async def download_all_transcripts(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Downloads all of a user's transcripts from S3 into a single ZIP file."""
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
                zipf.writestr(arcname, obj['Body'].read())
            except ClientError:
                print(
                    f"Skipping {transcript_s3_key}, not found in S3 during ZIP creation.")
                continue

    memory_file.seek(0)
    return StreamingResponse(
        memory_file,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={user.email}_transcripts.zip"}
    )
