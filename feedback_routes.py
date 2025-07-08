from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from datetime import datetime

# Local application imports
from models import User, Feedback  # Import the new Feedback model
from dependencies import get_db     # Correctly import get_db
from auth import get_current_user
from config import settings

router = APIRouter()


@router.post("/api/feedback")
def submit_feedback(
    message_body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Saves user feedback into the database."""
    message = message_body.get("message")
    if not message:
        raise HTTPException(
            status_code=400, detail="Feedback message cannot be empty.")

    try:
        new_feedback = Feedback(
            email=user.email,
            user_id=user.id,
            message=message,
            timestamp=datetime.utcnow()
        )
        db.add(new_feedback)
        db.commit()
        return {"message": "Feedback submitted successfully. Thank you!"}
    except Exception as e:
        # Log the error for debugging
        print(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail="Could not save feedback.")


@router.get("/api/feedback")
def get_feedback(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Allows an admin to retrieve all feedback from the database."""
    # Use the admin_emails list from settings for secure admin checking
    if current_user.email not in settings.admin_emails:
        raise HTTPException(
            status_code=403, detail="Not authorized for this resource.")

    feedback_entries = db.query(Feedback).order_by(
        Feedback.timestamp.desc()).all()

    # Pydantic will automatically serialize the SQLAlchemy objects into JSON
    return feedback_entries
