from sqlalchemy import Column, Integer, Text, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.schema import Index

from app.database.session import Base


class SemanticCache(Base):
    __tablename__ = "semantic_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    question = Column(Text)
    answer = Column(Text)
    embedding = Column(Vector(1536))
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index(
            "idx_semantic_cache_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class UnansweredQuestion(Base):
    __tablename__ = "unanswered_questions"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    role = Column(String(50))
    segment = Column(String(50))
    anonymous_id = Column(String(100))
    user_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    occurrences = Column(Integer, default=1)

    __table_args__ = (
        Index("idx_unanswered_created", "created_at"),
        Index("idx_unanswered_question", "question"),
    )