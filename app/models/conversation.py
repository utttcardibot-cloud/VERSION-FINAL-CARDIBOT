from sqlalchemy import Column, Integer, DateTime, String, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.database.session import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, nullable=True, index=True)

    anonymous_id = Column(String, nullable=True, index=True)

    title = Column(String, nullable=False, default="Nueva conversación")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Estado conversacional persistente
    state = Column(
        JSONB,
        nullable=False,
        default=dict  # importante usar callable
    )

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    # Índices opcionales recomendados
    __table_args__ = (
        Index("idx_conversations_user_id", "user_id"),
        Index("idx_conversations_anonymous_id", "anonymous_id"),
    )