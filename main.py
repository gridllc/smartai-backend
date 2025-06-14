from fastapi import FastAPI, UploadFile, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import shutil, os, sqlite3, hashlib, jwt, zipfile, uuid
from datetime import datetime, timedelta
from typing import Optional
from pinecone_sdk import search_similar_chunks
from upload_processor import transcribe_audio, get_openai_client

SECRET_KEY = "secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

app = FastAPI()

UPLOAD_DIR = "uploads"
TRANSCRIPTS_DIR = "transcripts"
DB_PATH = "transcripts.db"
STATIC_DIR = "static"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# ---------- DB INIT ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transcripts (
                    filename TEXT PRIMARY KEY,
                    transcript TEXT,
                    timestamp TEXT,
                    username TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    full_name TEXT,
                    password_hash TEXT,
                    is_admin INTEGER DEFAULT 0
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS invites (
                    code TEXT PRIMARY KEY,
                    used INTEGER DEFAULT 0
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    question TEXT,
                    timestamp TEXT
                )''')
    def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (username, full_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
              ("patrick", "Patrick", hash_pw("1Password"), 1))
    c.execute("INSERT OR IGNORE INTO users (username, full_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
              ("david", "David at Cisco", hash_pw("2Password"), 0))
    conn.commit()
    conn.close()

init_db()

# ---------- UTILS ----------
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def authenticate_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    return row and hash_pw(password) == row[0]

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def is_admin(username: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == 1

# ---------- MODELS ----------
class AskRequest(BaseModel):
    question: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class RegisterRequest(BaseModel):
    username: str
    full_name: str
    password: str
    invite_code: str

# ---------- ROUTES ----------
@app.post("/invite")
async def create_invite(current_user: str = Depends(get_current_user)):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admins only")
    code = str(uuid.uuid4())[:8]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO invites (code) VALUES (?)", (code,))
    conn.commit()
    conn.close()
    return {"invite_code": code}

@app.post("/register")
async def register_user(data: RegisterRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT used FROM invites WHERE code = ?", (data.invite_code,))
    row = c.fetchone()
    if not row or row[0] == 1:
        raise HTTPException(status_code=403, detail="Invalid or used invite")
    c.execute("INSERT INTO users (username, full_name, password_hash, is_admin) VALUES (?, ?, ?, 0)",
              (data.username, data.full_name, hash_pw(data.password)))
    c.execute("UPDATE invites SET used = 1 WHERE code = ?", (data.invite_code,))
    conn.commit()
    conn.close()
    return {"status": "Account created"}

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if not authenticate_user(form_data.username, form_data.password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/change-password")
async def change_password(data: ChangePasswordRequest, username: str = Depends(get_current_user)):
    if not authenticate_user(username, data.old_password):
        raise HTTPException(status_code=403, detail="Incorrect old password")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hash_pw(data.new_password), username))
    conn.commit()
    conn.close()
    return {"message": "Password updated successfully."}

@app.post("/ask")
async def ask_question(request: AskRequest, username: str = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO activity_log (username, question, timestamp) VALUES (?, ?, ?)",
              (username, request.question, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    relevant_chunks = search_similar_chunks(request.question, top_k=5)
    context_block = "\n\n".join([chunk["text"] for chunk in relevant_chunks])
    system_prompt = (
        "You are a helpful assistant. Use the following transcript snippets to answer the question.\n\n"
        f"{context_block}\n\n"
        "Question: " + request.question
    )
    client = get_openai_client()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": system_prompt}],
        temperature=0.3,
        max_tokens=500
    )
    return {"answer": response.choices[0].message.content, "sources": relevant_chunks}

@app.get("/admin/activity")
async def view_activity(current_user: str = Depends(get_current_user)):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admins only")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, question, timestamp FROM activity_log ORDER BY timestamp DESC")
    rows = [dict(username=row[0], question=row[1], timestamp=row[2]) for row in c.fetchall()]
    conn.close()
    return rows