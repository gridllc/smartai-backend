import os
import sqlite3
from fastapi import FastAPI, UploadFile, Depends, HTTPException, Header
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
from datetime import datetime
from upload_processor import transcribe_audio, get_openai_client
from pinecone_sdk import search_similar_chunks

app = FastAPI()

# Directories
UPLOAD_DIR = "uploads"
TRANSCRIPT_DIR = "transcripts"
STATIC_DIR = "static"
DB_PATH = "transcripts.db"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# Mount static files
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TEMP: Drop and recreate users table to fix broken schema
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS transcripts (
        filename TEXT PRIMARY KEY,
        transcript TEXT,
        timestamp TEXT
    )""")

    c.execute("DROP TABLE IF EXISTS users")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        password TEXT
    )""")

    c.execute("INSERT INTO users (email, password) VALUES (?, ?)", ("patrick@gridllc.net", "1Password"))
    c.execute("INSERT INTO users (email, password) VALUES (?, ?)", ("davidgriffin99@gmail.com", "2Password"))

    conn.commit()
    conn.close()

init_db()

class AskRequest(BaseModel):
    question: str

class LoginRequest(BaseModel):
    email: str
    password: str

def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    token = authorization.replace("Bearer ", "")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE email = ?", (token,))
    user = c.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return token

@app.post("/login")
async def login(payload: LoginRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE email = ?", (payload.email,))
    row = c.fetchone()
    conn.close()
    if not row or row[0] != payload.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": payload.email}

@app.post("/register")
async def register(payload: LoginRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE email = ?", (payload.email,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="User already exists")
    c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (payload.email, payload.password))
    conn.commit()
    conn.close()
    return {"message": "User registered"}

@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")

@app.post("/upload-and-transcribe")
async def upload_and_transcribe(file: UploadFile, user: str = Depends(verify_token)):
    file_location = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    transcript = transcribe_audio(file_location)
    with open(os.path.join(TRANSCRIPT_DIR, file.filename + ".txt"), "w", encoding="utf-8") as f:
        f.write(transcript)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("REPLACE INTO transcripts (filename, transcript, timestamp) VALUES (?, ?, ?)",
              (file.filename, transcript, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    return {"filename": file.filename, "transcript": transcript}

@app.get("/api/history")
async def history(user: str = Depends(verify_token)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT filename FROM transcripts")
    files = [row[0] for row in c.fetchall()]
    conn.close()
    return {"files": files}

@app.get("/api/transcript/{filename}")
async def get_transcript(filename: str, user: str = Depends(verify_token)):
    filepath = os.path.join(TRANSCRIPT_DIR, filename + ".txt")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return {"filename": filename, "transcript": f.read()}
    return JSONResponse(status_code=404, content={"error": "Transcript not found"})

@app.get("/api/download/{filename}")
async def download_transcript(filename: str, user: str = Depends(verify_token)):
    filepath = os.path.join(TRANSCRIPT_DIR, filename + ".txt")
    if os.path.exists(filepath):
        return FileResponse(filepath, media_type='application/octet-stream', filename=filename + ".txt")
    return JSONResponse(status_code=404, content={"error": "Transcript file not found"})

@app.delete("/api/delete/{filename}")
async def delete_transcript(filename: str, user: str = Depends(verify_token)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM transcripts WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()

    txt_path = os.path.join(TRANSCRIPT_DIR, filename + ".txt")
    if os.path.exists(txt_path):
        os.remove(txt_path)

    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    return {"status": "deleted"}

@app.post("/ask")
async def ask_question(request: AskRequest, user: str = Depends(verify_token)):
    question = request.question
    relevant_chunks = search_similar_chunks(question, top_k=5)
    context_block = "\n\n".join([chunk["text"] for chunk in relevant_chunks])
    system_prompt = (
        "You are a helpful assistant. Use the following transcript snippets to answer the question.\n\n"
        f"{context_block}\n\n"
        "Question: " + question
    )
    client = get_openai_client()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": system_prompt}],
        temperature=0.3,
        max_tokens=500
    )
    return {
        "answer": response.choices[0].message.content,
        "sources": relevant_chunks
    }

@app.get("/ask-stream")
async def ask_stream(question: str, user: str = Depends(verify_token)):
    relevant_chunks = search_similar_chunks(question, top_k=5)
    context_block = "\n\n".join([chunk["text"] for chunk in relevant_chunks])
    system_prompt = (
        "You are a helpful assistant. Use the following transcript snippets to answer the question.\n\n"
        f"{context_block}\n\n"
        "Question: " + question
    )
    client = get_openai_client()

    async def event_generator():
        stream = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.3,
            max_tokens=500,
            stream=True
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield f"data: {chunk.choices[0].delta.content}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/uploads/{filename}")
async def get_uploaded_file(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return JSONResponse(status_code=404, content={"error": "File not found"})

@app.get("/static/{filename}")
async def get_static_file(filename: str):
    file_path = os.path.join(STATIC_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return JSONResponse(status_code=404, content={"error": "File not found"})
