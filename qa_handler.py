import os
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("smartai-transcripts")

EMBED_MODEL = "text-embedding-3-small"
GPT_MODEL = "gpt-3.5-turbo"

def get_answer(question: str, top_k: int = 5) -> str:
    # Step 1: Embed the user question
    embedding = client.embeddings.create(
        input=question,
        model=EMBED_MODEL
    ).data[0].embedding

    # Step 2: Query Pinecone for similar chunks
    results = index.query(vector=embedding, top_k=top_k, include_metadata=True)

    # Step 3: Combine matching transcript chunks
    context = "\n\n".join([match.metadata["text"] for match in results.matches])

    # Step 4: Ask OpenAI using retrieved context
    prompt = f"""You are an assistant trained on transcripts. Use the context below to answer the question.

Context:
{context}

Question:
{question}

Answer:"""

    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return response.choices[0].message.content.strip()

# Run a test
if __name__ == "__main__":
    answer = get_answer("What was said about the onboarding process?")
    print("🧠 Answer:", answer)

