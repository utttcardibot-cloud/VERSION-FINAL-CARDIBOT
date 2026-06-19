import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    EMBEDDING_MODEL = "text-embedding-3-small"
    CHAT_MODEL = "gpt-5-mini"

    VECTOR_DIM = 1536  # OpenAI embeddings

settings = Settings()
