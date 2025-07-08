import os
import json
from typing import List
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file for local development.
# This needs to be at the top to run before Settings is defined.
load_dotenv()


class Settings(BaseSettings):
    """
    Manages all application settings, loading from environment variables.
    """

    # --- Required Settings (App will fail to start if these are not set) ---
    database_url: str = Field(..., env="DATABASE_URL")
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    aws_access_key_id: str = Field(..., env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(..., env="AWS_SECRET_ACCESS_KEY")
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")

    # Email configuration
    email_host: str = Field(..., env="SMARTAI_SMTP_HOST")
    email_port: int = Field(..., env="SMARTAI_SMTP_PORT")
    email_username: str = Field(..., env="SMARTAI_SMTP_USER")
    email_password: str = Field(..., env="SMARTAI_SMTP_PASS")

    # --- Optional Settings with Defaults ---
    aws_region: str = Field(default="us-west-1", env="AWS_REGION")
    s3_bucket: str = Field(default="smartai-transcripts-pg", env="S3_BUCKET")
    admin_emails: List[str] = Field(default_factory=list, env="ADMIN_EMAILS")
    app_name: str = Field(default="Transcription Service", env="APP_NAME")
    debug: bool = Field(default=False, env="DEBUG")

    # File paths and limits
    static_dir: str = "static"
    transcript_dir: str = "transcripts"
    max_file_size: int = 100_000_000
    allowed_extensions: List[str] = [
        ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4", ".mov", ".mkv", ".avi"
    ]

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
                # If JSON fails, fall back to comma-separated string
                return [email.strip() for email in v.split(',') if email.strip()]
        if isinstance(v, list):
            return v
        return []

    # This inner class is the modern and recommended way to configure Pydantic's behavior.
    # It correctly handles loading from both .env files and the server environment.
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Create a single settings instance to be used throughout the application
settings = Settings()

# A final check to provide a clear startup message in the logs.
# This will now run AFTER the settings have been successfully validated.
print("✅ Configuration loaded successfully.")
print(f"   - SMTP User: {settings.email_username}")
print(f"   - SMTP Host: {settings.email_host}:{settings.email_port}")
