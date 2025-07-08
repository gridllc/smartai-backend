import os
import json
from typing import List, Optional
from pydantic import Field, validator, ValidationError
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file for local development.
load_dotenv()


class Settings(BaseSettings):
    """
    Defines the structure of our application settings.
    We will create an instance of this manually below.
    """
    # --- Required fields (will raise an error if not present) ---
    database_url: str
    openai_api_key: str
    aws_access_key_id: str
    aws_secret_access_key: str
    jwt_secret_key: str
    email_host: str
    email_port: int
    email_username: str
    email_password: str

    # --- Optional settings with defaults ---
    # FIX: Mark these fields as Optional in the type hint.
    # This tells Pydantic that `None` is an acceptable initial value,
    # before the default is applied.
    aws_region: Optional[str] = "us-west-1"
    s3_bucket: Optional[str] = "smartai-transcripts-pg"
    admin_emails: Optional[List[str]] = []

    # These have defaults and are less likely to be environment-specific
    app_name: str = "Transcription Service"
    debug: bool = False
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
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [email.strip() for email in v.split(',') if email.strip()]
        return v

# --- Manual Settings Loading ---
# This approach is robust for deployment environments.


try:
    # 1. Gather all settings from the environment.
    settings_data = {
        "database_url": os.getenv("DATABASE_URL"),
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "jwt_secret_key": os.getenv("JWT_SECRET_KEY"),
        "email_host": os.getenv("SMARTAI_SMTP_HOST"),
        "email_port": os.getenv("SMARTAI_SMTP_PORT"),
        "email_username": os.getenv("SMARTAI_SMTP_USER"),
        "email_password": os.getenv("SMARTAI_SMTP_PASS"),
        # Load optionals too
        "aws_region": os.getenv("AWS_REGION"),
        "s3_bucket": os.getenv("S3_BUCKET"),
        "admin_emails": os.getenv("ADMIN_EMAILS"),
    }

    # Filter out keys where the value is None, so Pydantic uses the defaults.
    validated_data = {k: v for k, v in settings_data.items() if v is not None}

    # 2. Create and validate the settings instance.
    settings = Settings(**validated_data)

    print("✅ Configuration loaded successfully.")
    print(f"   - SMTP User: {settings.email_username}")
    print(f"   - S3 Bucket: {settings.s3_bucket}")

except ValidationError as e:
    print("❌ FATAL: Configuration validation failed. Check your environment variables.")
    for error in e.errors():
        # Provide a clearer error for missing required fields
        if error['type'] == 'missing':
            print(
                f"   - REQUIRED field '{error['loc'][0]}' is not set in the environment.")
        else:
            print(f"   - Field '{error['loc'][0]}': {error['msg']}")
    raise SystemExit(e) from e
