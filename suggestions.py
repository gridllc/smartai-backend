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
# Make sure s3_utils is available or use boto3 directly as shown
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

        async with aiofiles.open(upload_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)

        transcript_text, segments, audio_url, transcript_url = await transcribe_audio(upload_path, unique_name)

        # --- FIX: Standardize segment JSON naming and upload to S3 ---
        base_name = os.path.splitext(unique_name)[0]
        segments_filename = f"{base_name}.json"
        segments_path = os.path.join("transcripts", segments_filename)
        segments_s3_key = f"transcripts/{segments_filename}"

        # Save segments JSON locally to be uploaded
        async with aiofiles.open(segments_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(segments, indent=2))
        
        # Upload segments JSON to S3
        s3_client = boto3.client("s3", region_name=settings.aws_region)
        s3_client.upload_file(segments_path, settings.s3_bucket, segments_s3_key)
        os.remove(segments_path) # Clean up local file

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


# --- FIX: Added :path to filename parameter ---
@router.get("/api/transcript/{filename:path}")
def get_transcript_from_s3(filename: str, current_user: User = Depends(get_current_user)):
    s3 = boto3.client("s3", region_name=settings.aws_region)
    base_name = os.path.splitext(filename)[0]

    try:
        txt_key = f"transcripts/{base_name}.txt"
        txt_obj = s3.get_object(Bucket=settings.s3_bucket, Key=txt_key)
        text = txt_obj["Body"].read().decode("utf-8")
    except Exception:
        raise HTTPException(status_code=404, detail="Transcript text not found.")

    # --- FIX: Standardized segment key naming ---
    segments_key = f"transcripts/{base_name}.json"
    try:
        seg_obj = s3.get_object(Bucket=settings.s3_bucket, Key=segments_key)
        segments = json.loads(seg_obj["Body"].read().decode("utf-8"))
    except Exception:
        segments = []

    return JSONResponse(content={"transcript": text, "segments": segments})

# --- FIX: Added :path to filename parameter ---
@router.delete("/api/delete/{filename:path}")
async def delete_transcript(filename: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    # Assuming s3_utils provides a configured client
    from s3_utils import s3 
    import traceback

    safe_name = os.path.basename(filename)
    base = os.path.splitext(safe_name)[0]

    try:
        # Delete from S3
        s3.delete_object(Bucket=settings.s3_bucket, Key=f"uploads/{safe_name}")
        s3.delete_object(Bucket=settings.s3_bucket, Key=f"transcripts/{base}.txt")
        s3.delete_object(Bucket=settings.s3_bucket, Key=f"transcripts/{base}.json")

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

# --- FIX: Added :path to filename parameter ---
@router.post("/api/transcript/{filename:path}/segments")
async def save_segments(filename: str, data: dict, user=Depends(get_current_user)):
    safe_filename = os.path.basename(filename)
    
    # --- FIX: Standardize naming and upload to S3 instead of local file ---
    base_name = os.path.splitext(safe_filename)[0]
    s3_key = f"transcripts/{base_name}.json"
    segments_content = json.dumps(data.get("segments", []), indent=2)

    try:
        s3 = boto3.client("s3", region_name=settings.aws_region)
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=segments_content,
            ContentType="application/json"
        )
        return {"message": "Segments updated successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save segments to S3: {str(e)}")

# Add ":path" to all other routes with a filename parameter for consistency
@router.get("/api/share/{filename:path}", response_model=None)
# ... (rest of function)

@router.get("/api/quiz/{filename:path}")
# ... (rest of function)

@router.post("/api/transcript/{filename:path}/note")
# ... (rest of function)

@router.get("/api/transcript/{filename:path}/note")
# ... (rest of function)
            
@router.post("/api/transcript/{filename:path}/auto-segment")
# ... (rest of function)

@router.delete("/api/quiz/{filename:path}/{timestamp}")
# ... (rest of function)
            
@router.patch("/api/quiz/{filename:path}")
# ... (rest of function)

# (The rest of your transcription_routes.py file remains the same)