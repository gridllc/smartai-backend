from fastapi import APIRouter, UploadFile, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
import os
import sqlite3
import json
import io
from zipfile import ZipFile
from datetime import datetime

from database import get_db
from auth import get_current_user
from upload_processor import transcribe_audio, get_openai_client
from utils import sanitize_filename
from pinecone_sdk import search_similar_chunks
from config import settings

router = APIRouter()


@router.get("/api/qa-history")
async def get_qa_history(user=Depends(get_current_user)):
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """SELECT question, answer, timestamp, sources_used 
               FROM qa_history 
               WHERE email = ? 
               ORDER BY id DESC 
               LIMIT 50""",
            (user.email,)
        )
        history = []
        for row in cursor.fetchall():
            history_item = dict(row)
            if history_item['sources_used']:
                try:
                    history_item['sources_used'] = json.loads(
                        history_item['sources_used'])
                except json.JSONDecodeError:
                    history_item['sources_used'] = []
            history.append(history_item)

    return {"history": history}


@router.get("/api/transcripts")
async def get_transcript_list(user=Depends(get_current_user)):
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """SELECT filename, file_size, upload_timestamp 
               FROM user_files 
               WHERE email = ? 
               ORDER BY upload_timestamp DESC""",
            (user.email,)
        )
        files = [dict(row) for row in cursor.fetchall()]

    return {"files": files}


@router.get("/api/share/{filename}")
async def get_shared_transcript(filename: str):
    safe_filename = sanitize_filename(filename)
    path = os.path.join(settings.transcript_dir, safe_filename)

    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Transcript not found")

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"transcript": content}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="Failed to read transcript")


@router.get("/api/download/all")
async def download_all_transcripts(user=Depends(get_current_user)):
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
    return StreamingResponse(memory_file, media_type="application/zip", headers=headers)
