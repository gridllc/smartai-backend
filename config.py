
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import List, Union
import json
import os


class Settings(BaseSettings):
    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # OpenAI
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")

    # JWT secret key
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")

    # Email configuration (optional)
    email_host: str = Field(default="", env="EMAIL_HOST")
    email_port: int = Field(default=587, env="EMAIL_PORT")
    email_username: str = Field(default="", env="EMAIL_USERNAME")
    email_password: str = Field(default="", env="EMAIL_PASSWORD")

    # Admin emails - handle both JSON array and comma-separated string
    admin_emails: List[str] = Field(default_factory=list, env="ADMIN_EMAILS")

    # App settings
    app_name: str = Field(default="Transcription Service", env="APP_NAME")
    debug: bool = Field(default=False, env="DEBUG")

    @validator('admin_emails', pre=True)
    def parse_admin_emails(cls, v):
        if not v:
            return []

        if isinstance(v, str):
            # Try to parse as JSON first
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

            # If JSON parsing fails, treat as comma-separated string
            return [email.strip() for email in v.split(',') if email.strip()]

        if isinstance(v, list):
            return v

        return []

    # Local file paths
    transcript_dir: str = "transcripts"
    static_dir: str = "static"
    db_path: str = "transcripts.db"
    activity_log_path: str = "activity.log"
    upload_dir: str = "uploads"
    max_file_size: int = 100_000_000
    allowed_extensions: List[str] = [
        ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4", ".mov", ".mkv", ".avi"
    ]

    class Config:
        env_file = ".env"
        case_sensitive = False


# Create settings instance
settings = Settings()
