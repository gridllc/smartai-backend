from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from database import get_db
from auth import get_current_user
from config import settings
from models import ActivityLog, UserFile

router = APIRouter()


def is_admin_user(email: str) -> bool:
    return email in settings.admin_emails


@router.get("/api/stats")
async def get_stats(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_admin_user(user.email):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Get user activity counts
    user_activity = db.query(
        ActivityLog.email,
        db.query(ActivityLog).filter(ActivityLog.email ==
                                     ActivityLog.email).count().label("activity_count")
    ).group_by(ActivityLog.email).all()

    # Convert to list of dicts
    user_activity_list = [{"email": email, "activity_count": count}
                          for email, count in user_activity]

    # Get upload statistics
    file_stats = db.query(
        db.query(UserFile).count().label("total_files"),
        db.query(db.func.sum(UserFile.file_size)).label("total_size"),
        db.query(db.func.avg(UserFile.file_size)).label("avg_size")
    ).first()._asdict()

    # Get recent activity
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_activity_query = db.query(
        ActivityLog.action,
        db.func.count(ActivityLog.action).label("count")
    ).filter(ActivityLog.timestamp > seven_days_ago).group_by(ActivityLog.action).all()

    recent_activity = [
        {"action": action, "count": count} for action, count in recent_activity_query
    ]

    return {
        "user_activity": user_activity_list,
        "file_statistics": file_stats,
        "recent_activity": recent_activity
    }


@router.get("/api/activity-log")
async def get_activity_log(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_admin_user(user.email):
        raise HTTPException(status_code=403, detail="Admin access required")

    log_entries = db.query(ActivityLog).order_by(
        ActivityLog.id.desc()).limit(100).all()
    log_list = [
        {
            "email": entry.email,
            "action": entry.action,
            "filename": entry.filename,
            "timestamp": entry.timestamp.isoformat(),
            "ip_address": entry.ip_address
        } for entry in log_entries
    ]

    return {"log": log_list}
