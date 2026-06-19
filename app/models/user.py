from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func

from app.database.session import Base


class User(Base):
    __tablename__ = "users"

    # =========================
    # IDENTIDAD
    # =========================
    id = Column(Integer, primary_key=True, index=True)

    email = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)

    role = Column(String, nullable=False, index=True)

    # (solo para flujos anónimos si los usas)
    anonymous_id = Column(String, unique=True, index=True, nullable=True)

    # =========================
    # VERIFICACIÓN DE CUENTA
    # =========================
    is_verified = Column(Boolean, default=False, nullable=False)

    verification_token = Column(String, nullable=True)

    # 🔥 ESTA ERA LA QUE FALTABA
    verification_expires_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # =========================
    # METADATOS
    # =========================
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
