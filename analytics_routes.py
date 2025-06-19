from fastapi import APIRouter, Depends, HTTPException
import sqlite3
from datetime import datetime
from database import get_db
from auth import get_current_user
from config import settings

router = APIRouter()


def is_admin_user(email: str) -> bool:
    return email in settings.admin_emails


@router.get("/api/stats")
async def get_stats(user=Depends(get_current_user)):
    if not is_admin_user(user.email):
        raise HTTPException(status_code=403, detail="Admin access required")

    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get user activity counts
        cursor.execute("""
            SELECT email, COUNT(*) as activity_count 
            FROM activity 
            GROUP BY email 
            ORDER BY activity_count DESC
        """)
        user_activity = [dict(row) for row in cursor.fetchall()]

        # Get upload statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_files,
                SUM(file_size) as total_size,
                AVG(file_size) as avg_size
            FROM user_files
        """)
        file_stats = dict(cursor.fetchone())

        # Get recent activity
        cursor.execute("""
            SELECT action, COUNT(*) as count 
            FROM activity 
            WHERE timestamp > datetime('now', '-7 days')
            GROUP BY action
        """)
        recent_activity = [dict(row) for row in cursor.fetchall()]

    return {
        "user_activity": user_activity,
        "file_statistics": file_stats,
        "recent_activity": recent_activity
    }


@router.get("/api/activity-log")
async def get_activity_log(user=Depends(get_current_user)):
    if not is_admin_user(user.email):
        raise HTTPException(status_code=403, detail="Admin access required")

    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT email, action, filename, timestamp, ip_address 
            FROM activity 
            ORDER BY id DESC 
            LIMIT 100
        """)
        log_entries = [dict(row) for row in cursor.fetchall()]

    return {"log": log_entries}
