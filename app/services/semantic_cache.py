from sqlalchemy import text
from app.services.embedding_service import EmbeddingService

embedding_service = EmbeddingService()

SIMILARITY_THRESHOLD = 0.92


def to_pgvector(vec):
    """
    Convierte lista Python a formato pgvector
    """
    return "[" + ",".join(map(str, vec)) + "]"


async def generate_embedding(question: str):
    """
    Genera embedding usando el servicio de embeddings
    """
    return await embedding_service.embed(question)


def search_semantic_cache(db, embedding):
    """
    Busca respuesta similar en semantic cache
    """

    embedding_str = to_pgvector(embedding)

    result = db.execute(text("""
        SELECT answer,
               1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM semantic_cache
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT 1
    """), {"embedding": embedding_str}).fetchone()

    if result and result.similarity >= SIMILARITY_THRESHOLD:
        return result.answer

    return None


def store_semantic_cache(db, question, answer, embedding):
    """
    Guarda respuesta en semantic cache
    """

    embedding_str = to_pgvector(embedding)

    db.execute(text("""
        INSERT INTO semantic_cache (question, embedding, answer)
        VALUES (:question, CAST(:embedding AS vector), :answer)
    """), {
        "question": question,
        "embedding": embedding_str,
        "answer": answer
    })

    db.commit()