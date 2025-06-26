import os
import subprocess
from uuid import uuid4
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI
import whisper
from s3_utils import upload_to_s3

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("smartai-transcripts")

EMBED_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 500  # characters per chunk

def chunk_text(text, chunk_size=CHUNK_SIZE):
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
    response = client.embeddings.create(
        input=text,
        model=EMBED_MODEL
    )
    return response.data[0].embedding


def process_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        full_text = f.read()

    chunks = chunk_text(full_text)
    print(
        f"\U0001F4C4 {len(chunks)} chunks found in {os.path.basename(filepath)}")

    to_upsert = []
    for chunk in chunks:
        embedding = embed_text(chunk)
        metadata = {
            "text": chunk,
            "source": os.path.basename(filepath)
        }
        to_upsert.append((str(uuid4()), embedding, metadata))

    index.upsert(vectors=to_upsert)
    print(f"\u2705 Uploaded {len(to_upsert)} vectors to Pinecone.")


def get_embedding_model():
    class Embedder:
        def embed_query(self, text: str):
            response = client.embeddings.create(
                input=[text],
                model=EMBED_MODEL
            )
            return response.data[0].embedding
    return Embedder()


def extract_audio(input_path, output_path):
    print(f"\U0001F3B7 Extracting audio from {input_path} to {output_path}")
    command = [
        "ffmpeg", "-y", "-i", input_path, "-vn",
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", output_path
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg error during extract_audio: {e.stderr}")
        raise


def get_openai_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


if __name__ == "__main__":
    transcript_dir = "transcripts"
    for file in os.listdir(transcript_dir):
        if file.endswith(".txt"):
            process_file(os.path.join(transcript_dir, file))


async def transcribe_audio(file_path: str, filename: str) -> tuple[str, list[dict], str, str, str]:
    print(f"\U0001F3A7 Transcribing audio from {file_path}")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    model = whisper.load_model("base")
    result = model.transcribe(file_path)

    print(f"\u2705 Transcription completed for {os.path.basename(file_path)}")

    full_text = result.get("text", "")
    segments = result.get("segments", [])
    base_name = os.path.splitext(filename)[0]

    # Save transcript locally
    transcript_filename = f"{base_name}.txt"
    transcript_path = os.path.join("transcripts", transcript_filename)
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    # Format segments
    formatted_segments = [
        {
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "text": seg["text"].strip()
        }
        for seg in segments
    ]

    # Save segments locally
    segments_filename = f"{base_name}.json"
    segments_path = os.path.join("transcripts", segments_filename)
    with open(segments_path, "w", encoding="utf-8") as f:
        json.dump(formatted_segments, f, indent=2)

    # Upload all assets to S3
    audio_s3_url = upload_to_s3(file_path, f"uploads/{filename}")
    transcript_s3_url = upload_to_s3(
        transcript_path, f"transcripts/{transcript_filename}")
    # Upload the segments file to S3
    upload_to_s3(segments_path, f"transcripts/{segments_filename}")

    return full_text, formatted_segments, audio_s3_url, transcript_s3_url, transcript_path

