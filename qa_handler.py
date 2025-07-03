from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from auth import get_current_user
from database import get_db
from models import User, QAHistory   # <-- add User here
import json
from typing import Dict, Any
import logging
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()


class QuestionRequest(BaseModel):
    question: str


@router.post("/ask")
async def ask_question(payload: QuestionRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Handles a user's question, performs a semantic search, and streams the answer.
    Placeholder logic.
    """
    question = payload.question.strip()
    if not question:
        return {"error": "No question provided"}

    logging.info(f"Received question: {question}")

    async def fake_streamer():
        try:
            yield "data: " + json.dumps({"type": "token", "data": "This "}) + "\n\n"
            yield "data: " + json.dumps({"type": "token", "data": "is a "}) + "\n\n"
            yield "data: " + json.dumps({"type": "token", "data": "streaming "}) + "\n\n"
            yield "data: " + json.dumps({"type": "token", "data": "response. "}) + "\n\n"
            sources_payload = {
                "type": "sources",
                "data": [{"source": "example.txt", "text": "This is example source text."}]
            }
            yield "data: " + json.dumps(sources_payload) + "\n\n"
        except Exception as e:
            logging.error(f"Streaming error: {e}")

    return StreamingResponse(fake_streamer(), media_type="text/event-stream")


@router.get("/history")
async def get_qa_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves the 50 most recent Q&A history records for the current user.
    """

    history_records = (
        db.query(QAHistory)
        .filter(QAHistory.user_id == user.id)
        .order_by(QAHistory.id.desc())
        .limit(50)
        .all()
    )

    history = []
    for item in history_records:
        try:
            sources = json.loads(
                item.sources_used) if item.sources_used else []
        except json.JSONDecodeError:
            sources = []  # fallback to empty list on JSON error

        history.append({
            "question": item.question,
            "answer": item.answer,
            "timestamp": item.timestamp.isoformat(),
            "sources_used": sources
        })

    return {"history": history}
