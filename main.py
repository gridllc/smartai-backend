import os
import logging
import subprocess

from fastapi import FastAPI, Depends, HTTPException, Request, Body
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Local Imports
from auth import get_current_user
from database import get_db
from models import UserFile
from auth_routes import router as auth_router
from qa_handler import router as qa_router
from transcription_routes import router as transcription_router

# --- Load Environment Variables ---
load_dotenv()

# router = APIRouter() # We will not use a separate router for this file

app = FastAPI()
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(transcription_router,
                   prefix="/transcription", tags=["transcription"])
app.include_router(qa_router, prefix="/qa", tags=["qa"])

# CORS (allow all for dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # dev
        "https://smartai-pg.onrender.com",  # production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload and transcripts directories exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("transcripts", exist_ok=True)
os.makedirs("segments", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/transcripts", StaticFiles(directory="transcripts"),
          name="transcripts")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # It's better to use logging than print for production
    logging.error(
        f"Unhandled error on request {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."}
    )


@app.post("/reset-password")
def reset_password(data: dict = Body(...)):
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email required")

    # (You can simulate or implement email sending here)
    print(f"Reset link sent to: {email}")

    return {"message": "Reset instructions sent"}

# Alembic migration trigger (optional, for one-click migration)


# --- Optional: Alembic Migrations ---
@app.post("/run-migrations", include_in_schema=False)
def run_migrations():
    try:
        # NOTE: This is generally not recommended for production.
        # Migrations should be run as a separate deployment step.
        subprocess.run(["alembic", "upgrade", "head"],
                       check=True, capture_output=True, text=True)
        return {"status": "success", "message": "Migrations applied."}
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500, detail=f"Migration failed: {e.stderr}")


# --- Uvicorn Runner ---
if __name__ == "__main__":
    import uvicorn
    # Use 8000 as a more standard default
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
