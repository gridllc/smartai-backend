import boto3
import os
from dotenv import load_dotenv

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "smartaibackend")

# Initialize S3 client
s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)


def upload_file_to_s3(local_path: str, s3_key: str):
    """Upload a file to the specified S3 bucket."""
    s3.upload_file(local_path, S3_BUCKET_NAME, s3_key)
    print(f"✅ Uploaded to S3: {s3_key}")


def download_file_from_s3(s3_key: str, local_path: str):
    """Download a file from S3 to a local path."""
    s3.download_file(S3_BUCKET_NAME, s3_key, local_path)
    print(f"⬇️ Downloaded from S3: {s3_key}")
