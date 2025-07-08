import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict

# Local application imports
from models import UserFile
from dependencies import get_db
# To potentially secure this route in the future
from auth import get_current_user


router = APIRouter()


@router.get("/api/share/{filename}")
async def get_shared_transcript(filename: str, db: Session = Depends(get_db)) -> Dict[str, str]:
    """
    Gets transcript content from the database for a shared link.
    This is a public endpoint, so it doesn't require a logged-in user.
    """
    # Sanitize filename just in case, though it's less critical with DB queries.
    safe_filename = os.path.basename(filename)

    # Query the database for the file by its filename.
    # This is much more secure and robust than reading from the filesystem.
    file_record = db.query(UserFile).filter(
        UserFile.filename == safe_filename).first()

    if not file_record:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # The UserFile model now stores the transcript text directly.
    # Return the transcript text, or an empty string if it's null.
    return {"transcript": file_record.transcript_text or ""}

# The "/api/download/all" route was also in your original share_routes.py,
# but it logically belongs in transcription_routes.py, where we have already
# corrected and placed it. So, we can remove it from this file to avoid duplicationBased on your file.
