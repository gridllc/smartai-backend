import os
import json
from typing import List
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file for local development. This remains important.
load_dotenv()


class Settings(BaseSettings):
    """
    Manages all application settings, loading from environment variables.
    This version includes a custom __init__ to forcefully load environment
    variables in stubborn deployment environments like Render.
    """

    # Define all fields as optional initially, as we will load them in __init__
    database_url: str = None
    openai_api_key: str = None
    aws_access_key_id: str = None
    aws_secret_access_key: str = None
    jwt_secret_key: str = None

    # Email configuration
    email_host: str = None
    email_port: int = None
    email_username: str = None
    email_password: str = None

    # --- Optional Settings with Defaults ---
    aws_region: str = "us-west-1"
    s3_bucket: str = "smartai-transcripts-pg"
    admin_emails: List[str] = []
    app_name: str = "Transcription Service"
    debug: bool = False

    # File paths and limits
    static_dir: str = "static"
    transcript_dir: str = "transcripts"
    max_file_size: int = 100_000_000
    allowed_extensions: List[str] = [
        ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4", ".mov", ".mkv", ".avi"
    ]

    def __init__(self, **kwargs):
        """
        Custom initializer to forcefully load environment variables.
        This bypasses Pydantic's automatic discovery, which is failing on Render.
        """
        super().__init__(**kwargs)
        # Manually load all required variables from the environment
        self.database_url = os.getenv("DATABASE_URL")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.jwt_secret_key = os.getenv("JWT_SECRET_KEY")
        self.email_host = os.getenv("SMARTAI_SMTP_HOST")
        # Add default for port
        self.email_port = int(os.getenv("SMARTAI_SMTP_PORT", 587))
        self.email_username = os.getenv("SMARTAI_SMTP_USER")
        self.email_password = os.getenv("SMARTAI_SMTP_PASS")

        # Manually load optional variables if they exist
        self.aws_region = os.getenv("AWS_REGION", self.aws_region)
        self.s3_bucket = os.getenv("S3_BUCKET", self.s3_bucket)
        admin_emails_str = os.getenv("ADMIN_EMAILS")
        if admin_emails_str:
            self.admin_emails = self.parse_admin_emails(admin_emails_str)

    @validator('admin_emails', pre=True, allow_reuse=True)
    def parse_admin_emails(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return [email.strip() for email in v.split(',') if email.strip()]
        if isinstance(v, list):
            return v
        return []

    class Config:
        # Keep this for Pydantic to know it can be configured
        case_sensitive = False


# Create a single settings instance to be used throughout the application
settings = Settings()

# A final check to provide a clear startup message in the logs.
# We will add a check here to make sure the variables were loaded.
if not all([settings.database_url, settings.openai_api_key, settings.jwt_secret_key, settings.email_username]):
    print("❌ FATAL: One or more required environment variables are missing after manual loading. Please check Render environment.")
else:
    print("✅ Configuration loaded successfully via manual __init__.")
    print(f"   - SMTP User: {settings.email_username}")
