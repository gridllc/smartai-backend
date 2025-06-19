import os
import json
import aiofiles
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from zipfile import ZipFile
import io
import sqlite3
from utils import sanitize_filename, is_admin_user, log_activity
from auth import get_current_user
from config import settings

router = APIRouter()


@router.get("/api/share/{filename}")
async def get_shared_transcript(filename: str):
    """Get transcript content with security validation."""
    safe_filename = sanitize_filename(filename)
    path = os.path.join(settings.transcript_dir, safe_filename)

    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Transcript not found")

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        return {"transcript": content}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="Failed to read transcript")


@router.get("/api/download/all")
async def download_all_transcripts(user=Depends(get_current_user)):
    """Download all user transcripts as ZIP."""
    memory_file = io.BytesIO()

    with sqlite3.connect(settings.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT filename FROM user_files WHERE email = ?",
            (user.email,)
        )
        user_files = [row[0] for row in cursor.fetchall()]

    with ZipFile(memory_file, 'w') as zipf:
        for filename in user_files:
            transcript_path = os.path.join(
                settings.transcript_dir, filename + ".txt")
            if os.path.exists(transcript_path):
                zipf.write(transcript_path, arcname=f"{filename}.txt")

    memory_file.seek(0)
    headers = {
        "Content-Disposition": f"attachment; filename={user.email}_transcripts.zip"}

    log_activity(user.email, "download_all")
    return StreamingResponse(memory_file, media_type="application/zip", headers=headers)
