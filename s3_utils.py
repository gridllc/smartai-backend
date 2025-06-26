# s3_utils.py
import boto3
from config import settings

s3 = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region
)


def upload_to_s3(local_path: str, s3_key: str) -> str:
    s3.upload_file(local_path, settings.s3_bucket, s3_key)
    url = f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{s3_key}"
    return url
