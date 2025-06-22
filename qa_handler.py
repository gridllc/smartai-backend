from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from auth import get_current_user
from database import get_db
from models import QAHistory
import json
from typing import Dict, Any
import logging
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/api/qa-history")
async def get_qa_history(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    history_records = (
        db.query(QAHistory)
        .filter(QAHistory.email == user.email)
        .order_by(QAHistory.id.desc())
        .limit(50)
        .all()
    )

    history = []
    for item in history_records:
        sources = []
        try:
            sources = json.loads(
                item.sources_used) if item.sources_used else []
        except json.JSONDecodeError:
            pass

        history.append({
            "question": item.question,
            "answer": item.answer,
            "timestamp": item.timestamp,
            "sources_used": sources
        })

    return {"history": history}
