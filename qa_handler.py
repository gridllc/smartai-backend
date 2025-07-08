from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from auth import get_current_user
# This is the only line that changes.
from dependencies import get_db
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
            # The 'sources_used' column is already JSON, no need to parse it again
            # if the database driver handles it correctly. If not, this is a safe fallback.
            if isinstance(item.sources_used, str):
                sources = json.loads(item.sources_used)
            elif item.sources_used:  # It's likely already a dict/list
                sources = item.sources_used
        except (json.JSONDecodeError, TypeError):
            pass  # Keep sources as empty list if parsing fails

        history.append({
            "question": item.question,
            "answer": item.answer,
            "timestamp": item.timestamp,
            "sources_used": sources
        })

    return {"history": history}
