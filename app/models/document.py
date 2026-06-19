# app/models/document.py

import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.session import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    file_name = Column(String(255), unique=True, nullable=False)

    category = Column(String(50), nullable=False)

    nombre = Column(String(255))
    puesto = Column(String(255))
    unidad_organica = Column("unidadorganica", String(255))

    created_at = Column(DateTime, server_default=func.now())

    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan"
    )