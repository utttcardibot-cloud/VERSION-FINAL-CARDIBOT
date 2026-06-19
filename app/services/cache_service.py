import os
import redis
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# TTL de respuestas (ej: 1 hora)
CACHE_TTL = 3600

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)


class CacheService:

    @staticmethod
    def _normalize_question(question: str) -> str:
        return question.strip().lower()

    @staticmethod
    def _generate_key(question: str) -> str:
        normalized = CacheService._normalize_question(question)
        hashed = hashlib.sha256(normalized.encode()).hexdigest()
        return f"qa:{hashed}"

    @classmethod
    def get_answer(cls, question: str):
        key = cls._generate_key(question)
        data = r.get(key)

        if data:
            logger.info("🔥 Cache HIT")
            return json.loads(data)

        logger.info("❌ Cache MISS")
        return None

    @classmethod
    def set_answer(cls, question: str, answer: str):
        key = cls._generate_key(question)

        r.setex(
            key,
            CACHE_TTL,
            json.dumps({
                "answer": answer
            })
        )