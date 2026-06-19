from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import logging
import re

from app.database.session import SessionLocal
from app.models.conversation import Conversation
from app.models.message import Message
from app.core.security import get_current_user
from app.rag.pipeline import RAGPipeline

from app.services.cache_service import CacheService
from app.services.semantic_cache import (
    generate_embedding,
    search_semantic_cache,
    store_semantic_cache,
)

# =========================================
# VERSION PRUEBA SERVIDOR 22-05-2026
# CAMBIO PARA VALIDAR RELOAD
# =========================================

router = APIRouter(prefix="/conversations", tags=["conversations"])

logger = logging.getLogger(__name__)

# =====================================================
# ROLE → SEGMENT MAP
# =====================================================

ROLE_CATEGORY_MAP = {
    "admin": None,
    "student": "alumnos",
    "parent": "padres",
}

# =====================================================
# CONFIG
# =====================================================

MAX_QUESTION_LENGTH = 1000

FORBIDDEN_PATTERNS = [
    r";",
    r"--",
    r"/\*",
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bALTER\b",
]

PROMPT_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "system prompt",
    "reveal prompt",
    "token",
    "password",
    "bash",
    "sudo",
]

#  NUEVO — detectar groserías
TOXIC_PATTERNS = [
    r"\bpendej[o|a]\b",
    r"\bidiota\b",
    r"\bestupid[o|a]\b",
    r"\bchingad[oa]\b",
    r"\bputa\b",
    r"\bputo\b",
    r"\bpinche\b",
    r"\bverga\b",
    r"\bcabr[oó]n\b",
    r"\bculer[o|a]\b",
]

# =====================================================
# DB
# =====================================================


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================
# UTILIDADES
# =====================================================


def sanitize_text(text: str):
    return text.replace("\x00", "").strip()


def contains_toxic_language(text: str):

    text = text.lower()

    for pattern in TOXIC_PATTERNS:
        if re.search(pattern, text):
            return True

    return False


def validate_question(text: str):

    if len(text) > MAX_QUESTION_LENGTH:
        raise HTTPException(400, "La pregunta es demasiado larga")

    text_lower = text.lower()

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text_lower):
            raise HTTPException(400, "Entrada inválida detectada")

    for word in PROMPT_INJECTION_PATTERNS:
        if word in text_lower:
            raise HTTPException(400, "Consulta no permitida")


def generate_title(question: str):

    title = question.strip()
    title = re.sub(r"\s+", " ", title)

    return title[:80]


def should_cache_answer(answer: str):

    answer_lower = answer.lower()

    fallback_patterns = [
        "no puedo confirmar",
        "no se encontró información",
        "no está disponible en el contexto",
        "error interno",
        "no se pudo generar respuesta",
        "como asistente virtual",
        "no dispongo de información",
        "no tengo información",
        "no cuento con información",
        "no tengo datos sobre",
    ]

    if any(p in answer_lower for p in fallback_patterns):
        return False

    if len(answer) < 40:
        return False

    return True


# =====================================================
# GUARDAR PREGUNTAS NO RESPONDIDAS
# =====================================================


def register_unanswered_question(
    db: Session,
    question: str,
    role: str | None = None,
    segment: str | None = None,
    user_id: int | None = None,
):

    question = question.lower().strip()

    existing = db.execute(
        text("""
            SELECT id, occurrences
            FROM unanswered_questions
            WHERE question = :question
        """),
        {"question": question},
    ).fetchone()

    if existing:

        db.execute(
            text("""
                UPDATE unanswered_questions
                SET occurrences = occurrences + 1
                WHERE id = :id
            """),
            {"id": existing.id},
        )

    else:

        db.execute(
            text("""
                INSERT INTO unanswered_questions
                (question, role, segment, user_id)
                VALUES (:question, :role, :segment, :user_id)
            """),
            {
                "question": question,
                "role": role,
                "segment": segment,
                "user_id": user_id,
            },
        )

    db.commit()


# =====================================================
# CREAR CONVERSACIÓN
# =====================================================


@router.post("", status_code=status.HTTP_201_CREATED)
def create_conversation(
    title: str = Query("Nueva conversación"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    conversation = Conversation(
        user_id=current_user["user_id"],
        title=title.strip(),
        state={},
        created_at=datetime.utcnow(),
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return {
        "conversation_id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
    }


# =====================================================
# LISTAR CONVERSACIONES
# =====================================================


@router.get("")
def list_conversations(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user["user_id"])
        .order_by(Conversation.created_at.desc())
        .all()
    )

    return conversations


# =====================================================
# MENSAJES
# =====================================================


@router.get("/{conversation_id}/messages")
def get_messages(
    conversation_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user["user_id"],
        )
        .first()
    )

    if not conversation:
        raise HTTPException(404, "Conversación no encontrada")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )

    return messages


# =====================================================
# ASK
# =====================================================

@router.post("/{conversation_id}/ask")
async def ask_in_conversation(
    conversation_id: int,
    question: str = Query(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    role = current_user.get("role")

    if role not in ["admin", "student", "parent"]:
        raise HTTPException(403, "No autorizado")

    question = sanitize_text(question)

    validate_question(question)

    # =============================
    # CONTEXTUAL SHORT ANSWERS
    # =============================

    contextual_short_answers = [
        "si",
        "sí",
        "no",
        "ok",
        "claro",
        "dale",
        "va",
        "aja",
        "si por favor",
        "sí por favor",
        "por favor",
    ]

    normalized_question = question.lower().strip()

    is_contextual_short = (
        normalized_question in contextual_short_answers
    )

    # =============================
    # VALIDAR CONVERSACIÓN
    # =============================

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user["user_id"],
        )
        .first()
    )

    if not conversation:
        raise HTTPException(
            404,
            "Conversación no encontrada"
        )

    if conversation.title == "Nueva conversación":

        conversation.title = generate_title(question)

    use_cache = role in ["student", "parent"]

    # =============================
    # REDIS CACHE
    # =============================

    cached = None

    if use_cache and not is_contextual_short:

        cached = CacheService.get_answer(question)

    if cached:

        db.add(
            Message(
                conversation_id=conversation_id,
                role="user",
                content=question,
                created_at=datetime.utcnow(),
            )
        )

        db.add(
            Message(
                conversation_id=conversation_id,
                role="bot",
                content=cached["answer"],
                created_at=datetime.utcnow(),
            )
        )

        db.commit()

        return {
            "conversation_id": conversation_id,
            "answer": cached["answer"],
            "source": "cache",
        }

    # =============================
    # SEMANTIC CACHE
    # =============================

    embedding = await generate_embedding(question)

    semantic_answer = None

    if not is_contextual_short:

        semantic_answer = search_semantic_cache(
            db,
            embedding,
        )

    if semantic_answer:

        db.add(
            Message(
                conversation_id=conversation_id,
                role="user",
                content=question,
                created_at=datetime.utcnow(),
            )
        )

        db.add(
            Message(
                conversation_id=conversation_id,
                role="bot",
                content=semantic_answer,
                created_at=datetime.utcnow(),
            )
        )

        db.commit()

        return {
            "conversation_id": conversation_id,
            "answer": semantic_answer,
            "source": "semantic_cache",
        }

    # =============================
    # GUARDAR MENSAJE USUARIO
    # =============================

    db.add(
        Message(
            conversation_id=conversation_id,
            role="user",
            content=question,
            created_at=datetime.utcnow(),
        )
    )

    db.commit()

    segment = ROLE_CATEGORY_MAP.get(role)

    # =============================
    # 🔥 RAG CON DB AISLADA
    # =============================

    rag_db = SessionLocal()

    try:

        rag = RAGPipeline(
            role=role,
            segment=segment,
            db=rag_db,
            state=conversation.state or {},
        )

        result = await rag.ask(
            question=question,
            conversation_id=conversation_id,
            user_id=current_user["user_id"],
            endpoint="conversations",
        )

    except Exception:

        rag_db.rollback()
        db.rollback()

        logger.exception("Error en RAG")

        db.add(
            Message(
                conversation_id=conversation_id,
                role="bot",
                content="Error interno procesando la consulta.",
                created_at=datetime.utcnow(),
            )
        )

        db.commit()

        raise HTTPException(
            500,
            "Error en RAG"
        )

    finally:

        rag_db.close()

    # =============================
    # RESPUESTA
    # =============================

    answer = result.get(
        "text",
        "No se pudo generar respuesta."
    )

    db.add(
        Message(
            conversation_id=conversation_id,
            role="bot",
            content=answer,
            created_at=datetime.utcnow(),
        )
    )

    conversation.state = result.get(
        "state",
        conversation.state,
    )

    db.commit()

    # =============================
    # CACHE + ANALYTICS
    # =============================

    if (
        should_cache_answer(answer)
        and not is_contextual_short
    ):

        store_semantic_cache(
            db=db,
            question=question,
            answer=answer,
            embedding=embedding,
        )

        if use_cache and not is_contextual_short:

            CacheService.set_answer(
                question,
                answer,
            )

    else:

        if (
            not contains_toxic_language(question)
            and not is_contextual_short
        ):

            register_unanswered_question(
                db=db,
                question=question,
                role=role,
                segment=segment,
                user_id=current_user["user_id"],
            )

    return {
        "conversation_id": conversation_id,
        "answer": answer,
        "source": result.get("source", "rag"),
    }
# =====================================================
# ELIMINAR CONVERSACIÓN
# =====================================================


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user["user_id"],
        )
        .first()
    )

    if not conversation:
        raise HTTPException(404, "Conversación no encontrada")

    db.query(Message).filter(Message.conversation_id == conversation_id).delete()

    db.delete(conversation)

    db.commit()

    return {"message": "Conversación eliminada correctamente"}


# =====================================================
# ELIMINAR TODAS LAS CONVERSACIONES
# =====================================================


@router.delete("")
def delete_all_conversations(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    user_id = current_user["user_id"]

    conversations = (
        db.query(Conversation.id).filter(Conversation.user_id == user_id).all()
    )

    conversation_ids = [c.id for c in conversations]

    if not conversation_ids:
        return {"message": "No hay conversaciones para eliminar"}

    db.query(Message).filter(Message.conversation_id.in_(conversation_ids)).delete(
        synchronize_session=False
    )

    db.query(Conversation).filter(Conversation.user_id == user_id).delete()

    db.commit()

    return {"message": "Todas las conversaciones fueron eliminadas correctamente"}
