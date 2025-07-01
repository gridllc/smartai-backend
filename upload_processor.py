import os
import json
import subprocess
from uuid import uuid4
from dotenv import load_dotenv

from openai import OpenAI
import whisper
import boto3
from botocore.exceptions import ClientError
from pinecone import Pinecone
from config import settings

# --- Load .env first ---
load_dotenv()

# --- Initialize Clients ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Modern Pinecone initialization
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("smartai-transcripts")

# S3 client
s3 = boto3.client("s3", region_name=settings.aws_region)

# --- Constants ---
EMBED_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 500

# --- Pinecone and Embedding Functions (Refactored for S3) ---


def chunk_text(text, chunk_size=CHUNK_SIZE):
    """Break text into smaller chunks."""
    chunks = []
    current = ""
    for line in text.splitlines():
        if len(current) + len(line) < chunk_size:
            current += line + "\n"
        else:
            chunks.append(current.strip())
            current = line + "\n"
    if current:
        chunks.append(current.strip())
    return chunks


def embed_text(text):
    """Generate OpenAI embeddings for a text."""
    response = client.embeddings.create(input=text, model=EMBED_MODEL)
    return response.data[0].embedding


def process_transcript_for_pinecone(s3_bucket: str, s3_key: str):
    """Embed and upsert transcript data from S3 into Pinecone."""
    try:
        obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        full_text = obj['Body'].read().decode('utf-8')
    except ClientError as e:
        print(f"❌ Could not retrieve {s3_key} from S3: {e}")
        return

    chunks = chunk_text(full_text)
    print(f"📄 Found {len(chunks)} chunks in {s3_key}")

    to_upsert = []
    for chunk in chunks:
        embedding = embed_text(chunk)
        metadata = {"text": chunk, "source": s3_key}
        to_upsert.append((str(uuid4()), embedding, metadata))

    if to_upsert:
        try:
            index.upsert(vectors=to_upsert)
            print(f"✅ Uploaded {len(to_upsert)} vectors to Pinecone.")
        except Exception as e:
            print(f"❌ Pinecone upsert failed: {e}")

# --- Main Audio Transcription Function (Optimized for S3) ---


async def transcribe_audio(file_path: str, filename: str):
    """
    Transcribe an audio file and upload its assets to S3,
    then optionally process for semantic search.
    """
    print(f"🎧 Transcribing: {file_path}")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    # 1. Transcribe audio using Whisper
    model = whisper.load_model("base")
    result = model.transcribe(file_path)
    print(f"✅ Transcription complete for {filename}")

    full_text = result.get("text", "")
    segments = result.get("segments", [])
    base_name = os.path.splitext(filename)[0]

    # 2. Prepare content and S3 keys
    transcript_key = f"transcripts/{base_name}.txt"
    segments_key = f"transcripts/{base_name}.json"
    audio_key = f"uploads/{filename}"

    formatted_segments = [
        {"start": round(seg["start"], 2), "end": round(
            seg["end"], 2), "text": seg["text"].strip()}
        for seg in segments
    ]

    # 3. Upload all assets directly to S3
    try:
        s3.upload_file(file_path, settings.s3_bucket, audio_key)

        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=transcript_key,
            Body=full_text.encode('utf-8'),
            ContentType="text/plain",
        )

        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=segments_key,
            Body=json.dumps(formatted_segments, indent=2).encode('utf-8'),
            ContentType="application/json",
        )

        print(f"✅ Uploaded audio, transcript, segments to S3 for {filename}")

    except ClientError as e:
        print(f"❌ S3 upload failed: {e}")
        raise

    # Push to Pinecone
    process_transcript_for_pinecone(settings.s3_bucket, transcript_key)

    # Compose S3 URLs for return
    audio_s3_url = f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{audio_key}"
    transcript_s3_url = f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{transcript_key}"

    return full_text, formatted_segments, audio_s3_url, transcript_s3_url, ""


def get_embedding_model():
    """Embedding helper (compatibility with legacy code)"""
    class Embedder:
        def embed_query(self, text: str):
            response = client.embeddings.create(
                input=[text], model=EMBED_MODEL)
            return response.data[0].embedding
    return Embedder()


def extract_audio(input_path, output_path):
    """Extract audio using ffmpeg."""
    print(f"🎷 Extracting audio from {input_path} to {output_path}")
    command = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", output_path
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg error: {e.stderr}")
        raise
