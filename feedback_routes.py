# feedback_routes.py (clean and modular)
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from models import User, UserFile, QAHistory
from database import get_db
from auth import get_current_user
from datetime import datetime
from sqlalchemy import func, cast, Date
import os
import csv
import json

router = APIRouter()

# ✅ Feedback Submission


@router.post("/api/feedback")
def submit_feedback(message: str = Body(...), user: User = Depends(get_current_user)):
    feedback_file = "feedback/feedback.json"
    os.makedirs("feedback", exist_ok=True)

    try:
        if os.path.exists(feedback_file):
            with open(feedback_file, "r") as f:
                data = json.load(f)
        else:
            data = []

        data.append({
            "email": user.email,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        })

        with open(feedback_file, "w") as f:
            json.dump(data, f, indent=2)

        return {"message": "Feedback submitted"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ Admin: View Feedback


@router.get("/api/feedback")
def get_feedback(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    feedback_file = "feedback/feedback.json"
    if not os.path.exists(feedback_file):
        return []

    with open(feedback_file, "r") as f:
        return json.load(f)
