from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import logging
import re
import json
import unicodedata

from app.database.session import SessionLocal
from app.models.session import Session as UserSession
from app.models.conversation import Conversation
from app.models.message import Message
from app.core.security import get_current_user
from app.rag.langchain_pipeline import LangChainRAGWrapper

from app.services.cache_service import CacheService
from app.services.redis_service import redis_client

from app.services.semantic_cache import (
    generate_embedding,
    search_semantic_cache,
    store_semantic_cache
)

# =========================================
# VERSION PRUEBA SERVIDOR 22-05-2026
# CAMBIO PARA VALIDAR RELOAD
# =========================================

router = APIRouter(prefix="/ask", tags=["rag"])
logger = logging.getLogger(__name__)

MAX_QUESTION_LENGTH = 1000


# =====================================================
# SEGURIDAD
# =====================================================

FORBIDDEN_PATTERNS = [
    r";", r"--", r"/\*", r"\bDROP\b", r"\bDELETE\b",
    r"\bINSERT\b", r"\bUPDATE\b", r"\bALTER\b",
]

PROMPT_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "system prompt",
    "reveal prompt",
    "token",
    "password",
    "execute",
    "bash",
    "cmd",
    "powershell",
    "sudo",
]

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

def sanitize_text(text: str) -> str:
    return text.replace("\x00", "").strip()


def contains_toxic_language(text: str) -> bool:

    text = text.lower()

    for pattern in TOXIC_PATTERNS:
        if re.search(pattern, text):
            return True

    return False


def validate_question(text: str):

    if len(text) > MAX_QUESTION_LENGTH:
        raise HTTPException(400, "La pregunta es demasiado larga")

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            raise HTTPException(400, "Entrada inválida detectada")

    for word in PROMPT_INJECTION_PATTERNS:
        if word in text.lower():
            raise HTTPException(400, "Consulta no permitida")


def validate_anonymous_id(anonymous_id: str):

    if not re.match(r"^[a-zA-Z0-9\-_]{10,100}$", anonymous_id):
        raise HTTPException(400, "anonymous_id inválido")


def should_cache_answer(answer: str) -> bool:

    normalized = answer.lower().strip()

    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = normalized.encode("ascii", "ignore").decode("utf-8")

    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)

    fallback_patterns = [
        "no puedo confirmar",
        "no se encontro informacion",
        "no esta disponible en el contexto",
        "error interno",
        "no se pudo generar respuesta",
        "como asistente virtual",
        "no dispongo de informacion",
        "no tengo informacion",
        "no cuento con informacion",
        "no tengo datos sobre"
    ]

    if any(pattern in normalized for pattern in fallback_patterns):
        return False

    if len(normalized) < 40:
        return False

    return True


# =====================================================
# REGISTRAR PREGUNTAS NO RESPONDIDAS
# =====================================================

def register_unanswered_question(
    db: Session,
    question: str,
    role: str | None = None,
    segment: str | None = None,
    anonymous_id: str | None = None,
    user_id: int | None = None,
):

    question = question.lower().strip()

    existing = db.execute(
        text("""
            SELECT id, occurrences
            FROM unanswered_questions
            WHERE question = :question
        """),
        {"question": question}
    ).fetchone()

    if existing:

        db.execute(
            text("""
                UPDATE unanswered_questions
                SET occurrences = occurrences + 1
                WHERE id = :id
            """),
            {"id": existing.id}
        )

    else:

        db.execute(
            text("""
                INSERT INTO unanswered_questions
                (question, role, segment, anonymous_id, user_id)
                VALUES (:question, :role, :segment, :anonymous_id, :user_id)
            """),
            {
                "question": question,
                "role": role,
                "segment": segment,
                "anonymous_id": anonymous_id,
                "user_id": user_id
            }
        )

    db.commit()


# =====================================================
# ENDPOINT
# =====================================================

@router.post("")
async def ask(
    question: str | None = Query(None),
    anonymous_id: str | None = Query(None),
    conversation_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _current_user: dict | None = Depends(get_current_user),
):

    try:

        # =========================
        # VALIDAR SESIÓN
        # =========================

        session: UserSession | None = None

        if anonymous_id:

            validate_anonymous_id(anonymous_id)

            cached_session = redis_client.get(
                f"anon_session:{anonymous_id}"
            )

            if not cached_session:
                raise HTTPException(
                    401,
                    "Sesión inválida o expirada"
                )

            data = json.loads(cached_session)

            if data["questions_used"] >= data["max_questions"]:
                raise HTTPException(
                    403,
                    "Límite de preguntas alcanzado"
                )

            session = UserSession(
                anonymous_id=anonymous_id,
                role="anonymous",
                segment=data["segment"],
                questions_used=data["questions_used"],
                max_questions=data["max_questions"],
                expires_at=datetime.fromisoformat(
                    data["expires_at"]
                )
            )

        elif _current_user:

            session = (
                db.query(UserSession)
                .filter(
                    UserSession.user_id == _current_user["user_id"],
                    UserSession.expires_at > datetime.utcnow(),
                )
                .order_by(UserSession.created_at.desc())
                .first()
            )

        if not session:
            raise HTTPException(
                401,
                "Sesión inválida o expirada"
            )

        # =========================
        # VALIDAR PREGUNTA
        # =========================

        if not question or not question.strip():
            raise HTTPException(
                400,
                "La pregunta no puede estar vacía"
            )

        question = sanitize_text(question)

        validate_question(question)

        # =========================
        # CONTEXTUAL SHORT ANSWERS
        # =========================

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
            "por favor"
        ]

        normalized_question = question.lower().strip()

        is_contextual_short = (
            normalized_question in contextual_short_answers
        )

        # =========================
        # CONVERSACIÓN
        # =========================

        if not conversation_id:

            conversation = Conversation(
                user_id=(
                    session.user_id
                    if session.role != "anonymous"
                    else None
                ),
                title="Conversación",
                state={},
                created_at=datetime.utcnow()
            )

            db.add(conversation)
            db.commit()
            db.refresh(conversation)

            conversation_id = conversation.id

        else:

            conversation = (
                db.query(Conversation)
                .filter(
                    Conversation.id == conversation_id
                )
                .first()
            )

            if not conversation:
                raise HTTPException(
                    404,
                    "Conversación no encontrada"
                )

        # =========================
        # CACHE SIMPLE
        # =========================

        use_cache = session.role in [
            "anonymous",
            "parent"
        ]

        cached = None

        if use_cache and not is_contextual_short:

            cached = CacheService.get_answer(question)

        if cached:

            db.add(Message(
                conversation_id=conversation_id,
                role="user",
                content=question
            ))

            db.add(Message(
                conversation_id=conversation_id,
                role="bot",
                content=cached["answer"]
            ))

            db.commit()

            return {
                "conversation_id": conversation_id,
                "question": question,
                "answer": cached["answer"],
                "source": "cache",
            }

        # =========================
        # SEMANTIC CACHE
        # =========================

        embedding = await generate_embedding(question)

        semantic_answer = None

        if not is_contextual_short:

            semantic_answer = search_semantic_cache(
                db,
                embedding
            )

        if semantic_answer:

            db.add(Message(
                conversation_id=conversation_id,
                role="user",
                content=question
            ))

            db.add(Message(
                conversation_id=conversation_id,
                role="bot",
                content=semantic_answer
            ))

            db.commit()

            return {
                "conversation_id": conversation_id,
                "question": question,
                "answer": semantic_answer,
                "source": "semantic_cache",
            }

        # =========================
        # GUARDAR MENSAJE USUARIO
        # =========================

        db.add(Message(
            conversation_id=conversation_id,
            role="user",
            content=question
        ))

        db.commit()

        # =========================
        # RAG AISLADO
        # =========================

        rag_db = SessionLocal()

        try:

            history_messages = (
                db.query(Message)
                .filter(
                    Message.conversation_id == conversation_id
                )
                .order_by(Message.id.asc())
                .limit(10)
                .all()
            )

            chat_history = []

            for msg in history_messages:

                chat_history.append({
                    "role": msg.role,
                    "content": msg.content
                })

            print("CHAT HISTORY:", chat_history)

            rag = LangChainRAGWrapper(
                conversation_id=conversation_id,
                role=session.role,
                segment=session.segment,
                db=rag_db,
                state=conversation.state or {}
            )

            result = await rag.ask(
                question=question,
                user_id=(
                    session.user_id
                    if session.role != "anonymous"
                    else anonymous_id
                ),
                endpoint="ask",
                chat_history=chat_history
            )

        except Exception:

            rag_db.rollback()
            db.rollback()

            logger.exception("Error en RAG")

            db.add(Message(
                conversation_id=conversation_id,
                role="bot",
                content="Error interno procesando la consulta."
            ))

            db.commit()

            raise HTTPException(
                500,
                "Error en RAG"
            )

        finally:
            rag_db.close()

        # =========================
        # RESPUESTA
        # =========================

        answer = result.get(
            "text",
            "No se pudo generar respuesta."
        )

        source = result.get("source", "rag")

        new_state = result.get(
            "state",
            conversation.state
        )

        try:

            db.add(Message(
                conversation_id=conversation_id,
                role="bot",
                content=answer
            ))

            conversation.state = new_state

            db.commit()

        except Exception:

            db.rollback()
            logger.exception(
                "Error guardando respuesta"
            )

        # =========================
        # CACHE + ANALYTICS
        # =========================

        print("ANSWER:", answer)
        print(
            "CACHE RESULT:",
            should_cache_answer(answer)
        )

        if (
            should_cache_answer(answer)
            and not is_contextual_short
        ):

            print("🔥 GUARDANDO CACHE 🔥")

            store_semantic_cache(
                db=db,
                question=question,
                answer=answer,
                embedding=embedding
            )

            if use_cache and not is_contextual_short:

                CacheService.set_answer(
                    question,
                    answer
                )

        else:

            print("🔥 ENTRÓ A UNANSWERED 🔥")

            if (
                not contains_toxic_language(question)
                and not is_contextual_short
            ):

                register_unanswered_question(
                    db=db,
                    question=question,
                    role=session.role,
                    segment=session.segment,
                    anonymous_id=anonymous_id,
                    user_id=(
                        session.user_id
                        if session.role != "anonymous"
                        else None
                    )
                )

        # =========================
        # CONTROL DE USO
        # =========================

        if anonymous_id:

            data["questions_used"] += 1

            redis_client.setex(
                f"anon_session:{anonymous_id}",
                21600,
                json.dumps(data)
            )

        return {
            "conversation_id": conversation_id,
            "question": question,
            "answer": answer,
            "source": source,
            "debug": result.get("debug", {})
        }

    except HTTPException:

        db.rollback()
        raise

    except Exception:

        db.rollback()

        logger.exception(
            "Error inesperado en /ask"
        )

        raise HTTPException(
            500,
            "Error interno procesando la solicitud"
        )