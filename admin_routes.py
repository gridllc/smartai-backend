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
    # Note: get_current_user returns a User object, not a dict.
    # We should access its attributes directly, e.g., current_user.email
    if current_user.email != "patrick@gridllc.net":
        return JSONResponse(status_code=403, content={"detail": "Not authorized"})

    total_users = db.query(User).count()
    total_files = db.query(UserFile).count()
    total_questions = db.query(QAHistory).count()

    # This join assumes QAHistory has a user_email column that matches User.email. This is correct.
    top_users = (
        db.query(User.email, db.func.count(QAHistory.id).label("count"))
        .join(User, User.email == QAHistory.email)
        .group_by(User.email)
        .order_by(db.desc("count"))
        .limit(10)
        .all()
    )

    result = {
        "total_users": total_users,
        "total_files": total_files,
        "total_questions": total_questions,
        "top_users": [{"email": email, "count": count} for email, count in top_users]
    }
    return result


@router.get("/api/admin/stats/uploads-by-date")
async def uploads_by_date(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user['email'] != "patrick@gridllc.net":
        return JSONResponse(status_code=403, content={"detail": "Not authorized"})

    result = (
        db.query(db.func.date(UserFile.upload_timestamp),
                 db.func.count(UserFile.id))
        .group_by(db.func.date(UserFile.upload_timestamp))
        .order_by(db.func.date(UserFile.upload_timestamp))
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
        # FIX: The columns are `email` and `upload_timestamp`.
        writer.writerow([f.email, f.filename,
                        f.upload_timestamp.strftime("%Y-%m-%d %H:%M:%S")])

    buffer.seek(0)
    # The frontend probably expects a direct response, not a JSON object.
    # Returning the CSV data directly with a proper content type is better.
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=admin_data_export.csv"})
