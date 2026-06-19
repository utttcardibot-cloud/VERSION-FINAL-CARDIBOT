from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import uuid

from app.database.session import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    file_name = Column(String(255), nullable=False)

    # 🔹 Índice global del chunk
    chunk_index = Column(Integer, nullable=False)

    # 🔥 Estructura semántica
    section_title = Column(String(500), nullable=True)
    section_index = Column(Integer, nullable=True)

    content = Column(Text, nullable=False)

    # 🔥 Embedding puede ser NULL hasta que el worker lo procese
    embedding = Column(Vector(1536), nullable=True)

    # 🔥 NUEVO: estado del procesamiento
    status = Column(String(20), default="pending", nullable=False)

    document = relationship(
        "Document",
        back_populates="chunks"
    )