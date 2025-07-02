import os
import logging
import subprocess

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from config import settings
from auth_routes import router as auth_router
from qa_handler import router as qa_router
from transcription_routes import router as transcription_router

# --- Load Environment Variables ---
load_dotenv()

# --- Initialize FastAPI App ---
app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://smartai-pg.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Ensure Directories Exist (for local temp files) ---
os.makedirs("uploads", exist_ok=True)

# --- Mount Static Files ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Include Routers ---
# Note: The prefixes here are important. They were inconsistent in your original files.
# The routes in transcription_routes.py already have "/api" in their path.
app.include_router(auth_router)
app.include_router(transcription_router)
app.include_router(qa_router)

# --- Root and Utility Endpoints ---


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
