# admin_routes.py (clean version)
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
from models import UserFile, QAHistory, User
from fastapi.responses import JSONResponse
from typing import List
from datetime import datetime
import csv
import os
from io import StringIO

router = APIRouter()


@router.get("/api/admin/analytics")
async def admin_analytics(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user['email'] != "patrick@gridllc.net":
        return JSONResponse(status_code=403, content={"detail": "Not authorized"})

    total_users = db.query(User).count()
    total_files = db.query(UserFile).count()
    total_questions = db.query(QAHistory).count()

    top_users = (
        db.query(User.email, QAHistory.user_email,
                 db.func.count(QAHistory.id).label("count"))
        .join(User, User.email == QAHistory.user_email)
        .group_by(QAHistory.user_email)
        .order_by(db.desc("count"))
        .limit(10)
        .all()
    )

    result = {
        "total_users": total_users,
        "total_files": total_files,
        "total_questions": total_questions,
        "top_users": [{"email": email, "count": count} for email, _, count in top_users]
    }
    return result


@router.get("/api/admin/stats/uploads-by-date")
async def uploads_by_date(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user['email'] != "patrick@gridllc.net":
        return JSONResponse(status_code=403, content={"detail": "Not authorized"})

    result = (
        db.query(UserFile.uploaded_at, db.func.count(UserFile.id))
        .group_by(UserFile.uploaded_at)
        .order_by(UserFile.uploaded_at)
        .all()
    )

    stats = [{"date": r[0].strftime("%Y-%m-%d"), "count": r[1]}
             for r in result]
    return stats


@router.get("/api/admin/export-csv")
async def export_admin_data(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user['email'] != "patrick@gridllc.net":
        return JSONResponse(status_code=403, content={"detail": "Not authorized"})

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Email", "Filename", "Uploaded At"])

    files = db.query(UserFile).all()
    for f in files:
        writer.writerow([f.user_email, f.filename,
                        f.uploaded_at.strftime("%Y-%m-%d %H:%M:%S")])

    buffer.seek(0)
    return {"csv_data": buffer.read()}
