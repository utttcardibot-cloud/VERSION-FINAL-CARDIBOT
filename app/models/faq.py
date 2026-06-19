from sqlalchemy import Column, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from app.database.session import Base


class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, index=True)

    # 🔹 contenido principal
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)

    # 🔹 clasificación
    category = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)

    # 🔥 variantes (JSONB)
    variantes = Column(JSONB, default=list)

    # 🔥 contexto organizacional
    nombre = Column(String(255), nullable=True)
    puesto = Column(String(255), nullable=True)
    unidadorganica = Column(String(255), nullable=True)