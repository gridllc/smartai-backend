# cleanup_routes.py

import os
import sqlite3
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from auth import get_current_user
from config import settings
from utils import is_admin_user, log_activity

router = APIRouter()


async def cleanup_old_files():
    """Delete files older than 30 days in upload and transcript directories."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    deleted_files = []

    for folder in [settings.upload_dir, settings.transcript_dir]:
        for filename in os.listdir(folder):
            path = os.path.join(folder, filename)
            if os.path.isfile(path):
                modified = datetime.utcfromtimestamp(os.path.getmtime(path))
                if modified < cutoff:
                    os.remove(path)
                    deleted_files.append(filename)

    return deleted_files


@router.delete("/api/cleanup")
async def manual_cleanup(user=Depends(get_current_user)):
    """Manually trigger cleanup of old files (admin only)."""
    if not is_admin_user(user.email):
        raise HTTPException(status_code=403, detail="Admin access required")

    deleted = await cleanup_old_files()
    log_activity(user.email, "manual_cleanup")
    return {"message": f"Deleted {len(deleted)} old files", "files": deleted}
