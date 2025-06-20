from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    upload_dir: str = "uploads"
    transcript_dir: str = "transcripts"
    static_dir: str = "static"
    db_path: str = "transcripts.db"
    activity_log_path: str = "activity.log"

    max_file_size: int = 100_000_000  # 100MB
    max_files_per_user: int = 50
    reset_token_expiry_hours: int = 24
    ffmpeg_timeout: int = 300

    allowed_extensions: List[str] = [
        ".wav", ".mp3", ".m4a", ".flac", ".ogg",
        ".mp4", ".mov", ".mkv", ".avi"
    ]

    admin_emails: List[str] = [
        "patrick@gridllc.net"
    ]

    class Config:
        env_file = ".env"


settings = Settings()
