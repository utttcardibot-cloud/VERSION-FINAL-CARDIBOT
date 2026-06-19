from sqlalchemy import Column, Integer, DateTime, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timedelta
from app.database.session import Base
import uuid


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(Integer, nullable=True)  # SIN ForeignKey
    anonymous_id = Column(String, nullable=True)

    role = Column(String, nullable=False)
    segment = Column(String(50), nullable=True)

    questions_used = Column(Integer, default=0)
    max_questions = Column(Integer, default=5)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
