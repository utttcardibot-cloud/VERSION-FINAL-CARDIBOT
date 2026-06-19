import asyncio
import logging
from typing import List

from openai import AsyncOpenAI
from app.core.config import settings
from app.core.rate_limiter import RateLimiter

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
logger = logging.getLogger(__name__)

# Control conservador
embedding_limiter = RateLimiter(max_calls=10, period=1.0)


class EmbeddingService:

    # ============================================================
    # Embedding individual (para query)
    # ============================================================

    async def embed(self, text: str) -> List[float]:

        if not text or not text.strip():
            raise ValueError("Texto vacío para embedding")

        return (await self._create_embedding([text]))[0]

    # ============================================================
    # Embedding batch (para ingestión)
    # ============================================================

    async def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
        max_retries: int = 3
    ) -> List[List[float]]:

        # Filtrar textos vacíos pero preservar orden
        cleaned_texts = []
        index_map = []

        for i, t in enumerate(texts):
            if t and t.strip():
                cleaned_texts.append(t)
                index_map.append(i)

        if not cleaned_texts:
            return []

        all_embeddings = [None] * len(texts)

        for i in range(0, len(cleaned_texts), batch_size):
            batch = cleaned_texts[i:i + batch_size]

            embeddings = await self._create_embedding(
                batch,
                max_retries=max_retries
            )

            for j, emb in enumerate(embeddings):
                original_index = index_map[i + j]
                all_embeddings[original_index] = emb

        return all_embeddings

    # ============================================================
    # Core embedding con retry
    # ============================================================

    async def _create_embedding(
        self,
        inputs: List[str],
        max_retries: int = 3
    ) -> List[List[float]]:

        attempt = 0

        while attempt < max_retries:
            try:
                await embedding_limiter.acquire()

                response = await client.embeddings.create(
                    model=settings.EMBEDDING_MODEL,
                    input=inputs
                )

                return [item.embedding for item in response.data]

            except Exception as e:
                attempt += 1
                logger.warning(
                    f"Error embedding intento {attempt}/{max_retries}: {str(e)}"
                )

                if attempt >= max_retries:
                    logger.error("Fallo definitivo generando embeddings")
                    raise

                # Backoff exponencial
                await asyncio.sleep(2 ** attempt)