from fastapi import APIRouter, HTTPException, Response, Query
from datetime import datetime, timedelta
import uuid
import json

from app.services.redis_service import redis_client

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_TTL = 21600  # 6 horas


# =====================================================
# CREAR SESIÓN ANÓNIMA
# =====================================================

@router.post("/anonymous")
def create_anonymous_session(
    response: Response,
    segment: str = Query("aspirantes")
):

    if segment not in ["aspirantes", "padres"]:
        raise HTTPException(
            status_code=400,
            detail="Segmento inválido"
        )

    anonymous_id = uuid.uuid4().hex

    expires_at = datetime.utcnow() + timedelta(seconds=SESSION_TTL)

    session_data = {
        "segment": segment,
        "questions_used": 0,
        "max_questions": 50,
        "expires_at": expires_at.isoformat()
    }

    redis_client.setex(
        f"anon_session:{anonymous_id}",
        SESSION_TTL,
        json.dumps(session_data)
    )

    response.set_cookie(
        key="anonymous_id",
        value=anonymous_id,
        httponly=True,
        secure=False,
        samesite="Lax"
    )

    return {
        "anonymous_id": anonymous_id,
        "role": "anonymous",
        "segment": segment,
        "max_questions": 50,
        "expires_at": expires_at
    }


# =====================================================
# VALIDAR SESIÓN
# =====================================================

@router.get("/anonymous/validate")
def validate_anonymous_session(anonymous_id: str):

    cached = redis_client.get(f"anon_session:{anonymous_id}")

    if not cached:
        raise HTTPException(
            status_code=401,
            detail="Sesión anónima inválida o expirada"
        )

    data = json.loads(cached)

    return {
        "anonymous_id": anonymous_id,
        "role": "anonymous",
        "segment": data["segment"],
        "questions_used": data["questions_used"],
        "max_questions": data["max_questions"],
        "expires_at": data["expires_at"]
    }


# =====================================================
# ELIMINAR SESIÓN
# =====================================================

@router.delete("/anonymous")
def delete_anonymous_session(anonymous_id: str):

    redis_client.delete(f"anon_session:{anonymous_id}")

    return {
        "message": "Sesión anónima eliminada"
    }