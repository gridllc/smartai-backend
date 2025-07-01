import pinecone
from config import settings
from botocore.exceptions import ClientError
import boto3
import whisper
from openai import OpenAI
from uuid import uuid4
import json
import subprocess
import os
from dotenv import load_dotenv

load_dotenv()   # <-- run dotenv ASAP


# --- Initialize Clients ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# Initialize Pinecone
pinecone.init(
    api_key=os.getenv("PINECONE_API_KEY"),
    # e.g. "us-west1-gcp" or similar
    environment=os.getenv("PINECONE_ENVIRONMENT"),
)

index = pinecone.Index("smartai-transcripts")
s3 = boto3.client("s3", region_name=settings.aws_region)

EMBED_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 500  # characters per chunk

# --- Pinecone and Embedding Functions (Refactored for S3) ---


def chunk_text(text, chunk_size=CHUNK_SIZE):
    """Chunks text into smaller pieces."""
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
    """Generates an embedding for a piece of text using OpenAI."""
    response = client.embeddings.create(input=text, model=EMBED_MODEL)
    return response.data[0].embedding


def process_transcript_for_pinecone(s3_bucket: str, s3_key: str):
    """
    Fetches a transcript from S3, chunks it, embeds it, and uploads to Pinecone.
    This replaces the old process_file function.
    """
    try:
        obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        full_text = obj['Body'].read().decode('utf-8')
    except ClientError as e:
        print(f"❌ Could not retrieve {s3_key} from S3: {e}")
        return

    chunks = chunk_text(full_text)
    print(f"\U0001F4C4 {len(chunks)} chunks found in {s3_key}")

    to_upsert = []
    for chunk in chunks:
        embedding = embed_text(chunk)
        # Use S3 key as the source
        metadata = {"text": chunk, "source": s3_key}
        to_upsert.append((str(uuid4()), embedding, metadata))

    if to_upsert:
    try:
        index.upsert(vectors=to_upsert)
        print(f"✅ Uploaded {len(to_upsert)} vectors to Pinecone for {s3_key}.")
    except Exception as e:
        print(f"❌ Pinecone upsert failed: {e}")


# --- Main Audio Transcription Function (Optimized for S3) ---

async def transcribe_audio(file_path: str, filename: str) -> tuple[str, list[dict], str, str, str]:
    """
    Transcribes an audio file, and uploads the audio, transcript, and segments
    directly to S3 without creating intermediate local files for the text outputs.
    """
    print(f"\U0001F3A7 Transcribing audio from {file_path}")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    # 1. Transcribe audio using Whisper
    model = whisper.load_model("base")
    result = model.transcribe(file_path)
    print(f"\u2705 Transcription completed for {os.path.basename(file_path)}")

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
        # Upload original audio file
        s3.upload_file(file_path, settings.s3_bucket, audio_key)
        audio_s3_url = f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{audio_key}"

        # Upload transcript text from memory
        s3.put_object(Bucket=settings.s3_bucket, Key=transcript_key,
                      Body=full_text.encode('utf-8'), ContentType='text/plain')
        transcript_s3_url = f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{transcript_key}"

        # Upload segments JSON from memory
        segments_json = json.dumps(formatted_segments, indent=2)
        s3.put_object(Bucket=settings.s3_bucket, Key=segments_key,
                      Body=segments_json.encode('utf-8'), ContentType='application/json')

        print(
            f"\u2705 Uploaded audio, transcript, and segments to S3 for {filename}")

    except ClientError as e:
        print(f"❌ S3 Upload failed: {e}")
        raise

    # 4. (Optional but Recommended) Process for semantic search
    # This can be done asynchronously in a real app (e.g., using Celery/RQ)
    process_transcript_for_pinecone(settings.s3_bucket, transcript_key)

    # 5. Return the results
    # The final `transcript_path` is no longer needed as it was temporary.
    return full_text, formatted_segments, audio_s3_url, transcript_s3_url, ""


# --- Helper/Legacy Functions ---

def get_embedding_model():
    """Returns an embedder class instance."""
    class Embedder:
        def embed_query(self, text: str):
            response = client.embeddings.create(
                input=[text], model=EMBED_MODEL)
            return response.data[0].embedding
    return Embedder()


def extract_audio(input_path, output_path):
    """Extracts audio using FFmpeg. (This function is fine as is)."""
    print(f"\U0001F3B7 Extracting audio from {input_path} to {output_path}")
    command = ["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec",
               "pcm_s16le", "-ar", "16000", "-ac", "1", output_path]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg error during extract_audio: {e.stderr}")
        raise
