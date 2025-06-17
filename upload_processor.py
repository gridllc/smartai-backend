import os
import subprocess
from uuid import uuid4
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI
import whisper

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("smartai-transcripts")

# Config
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
    print(f"📄 {len(chunks)} chunks found in {os.path.basename(filepath)}")

    to_upsert = []
    for chunk in chunks:
        embedding = embed_text(chunk)
        metadata = {
            "text": chunk,
            "source": os.path.basename(filepath)
        }
        to_upsert.append((str(uuid4()), embedding, metadata))

    index.upsert(vectors=to_upsert)
    print(f"✅ Uploaded {len(to_upsert)} vectors to Pinecone.")

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
    print(f"🎧 Extracting audio from {input_path} to {output_path}")
    command = [
        "ffmpeg", "-i", input_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", output_path
    ]
    subprocess.run(command, check=True)

def transcribe_audio(file_path):
    audio_path = file_path.rsplit(".", 1)[0] + ".wav"
    extract_audio(file_path, audio_path)
    model = whisper.load_model("base")
    result = model.transcribe(audio_path)
    return result["text"]

def get_openai_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

if __name__ == "__main__":
    transcript_dir = "transcripts"
    for file in os.listdir(transcript_dir):
        if file.endswith(".txt"):
            process_file(os.path.join(transcript_dir, file))
