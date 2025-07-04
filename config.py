import os
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import List, Optional
import json


class Settings(BaseSettings):
    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # OpenAI
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")

    # AWS
    aws_access_key_id: str = Field(..., env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(..., env="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="us-west-1", env="AWS_REGION")
    s3_bucket: str = Field(default="smartai-transcripts-pg", env="S3_BUCKET")

    # JWT
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")

    # Email
    email_host: str = Field(default="smtp.gmail.com", env="SMARTAI_SMTP_HOST")
    email_port: int = Field(default=587, env="SMARTAI_SMTP_PORT")
    email_username: str = Field(..., env="SMARTAI_SMTP_USER")
    email_password: Optional[str] = Field(None, env="SMARTAI_SMTP_PASS")

    # Admin emails
    admin_emails: List[str] = Field(default_factory=list, env="ADMIN_EMAILS")

    @validator('admin_emails', pre=True)
    def parse_admin_emails(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            try:
                return json.loads(v) if isinstance(json.loads(v), list) else [v]
            except json.JSONDecodeError:
                return [email.strip() for email in v.split(',') if email.strip()]
        if isinstance(v, list):
            return v
        return []

    # App
    app_name: str = Field(default="Transcription Service", env="APP_NAME")
    debug: bool = Field(default=False, env="DEBUG")

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

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "allow"
    }


settings = Settings()

# hard debug
print("✅ DEBUG: SMARTAI_SMTP_PASS =", settings.email_password)

if not settings.email_password:
    print("⚠️  WARNING: SMARTAI_SMTP_PASS is missing at runtime. Check your environment variables on Render!")
