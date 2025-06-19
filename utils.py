# utils.py

import os
import secrets
import hashlib
import sqlite3
from datetime import datetime
from config import settings


def sanitize_filename(filename: str) -> str:
    """Remove any unsafe characters from filenames."""
    base = os.path.basename(filename)
    safe = "".join(c for c in base if c.isalnum() or c in "._-")
    return safe or f"file_{secrets.token_hex(8)}"


def validate_file_extension(filename: str) -> bool:
    """Ensure file extension is within allowed list."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in settings.allowed_extensions


def is_admin_user(email: str) -> bool:
    return email in settings.admin_emails


def log_activity(email: str, action: str, filename: str = None, ip_address: str = None, user_agent: str = None):
    """Write user actions to both SQLite and a flat file."""
    timestamp = datetime.utcnow().isoformat()

    with sqlite3.connect(settings.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO activity (email, action, filename, timestamp, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (email, action, filename, timestamp, ip_address, user_agent))
        conn.commit()

    with open(settings.activity_log_path, "a") as f:
        f.write(
            f"{timestamp}|{email}|{action}|{filename or ''}|{ip_address or ''}\n")
