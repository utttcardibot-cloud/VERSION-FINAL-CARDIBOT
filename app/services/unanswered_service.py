from sqlalchemy.orm import Session
from sqlalchemy import text


def register_unanswered_question(
    db: Session,
    question: str,
    role: str | None = None,
    segment: str | None = None,
    anonymous_id: str | None = None,
    user_id: int | None = None,
):
    """
    Registra una pregunta que el sistema no pudo responder.

    Si la pregunta ya existe en la tabla, incrementa el contador de
    ocurrencias. Si no existe, crea un nuevo registro.
    """

    # verificar si la pregunta ya existe
    existing = db.execute(
        text("""
            SELECT id, occurrences
            FROM unanswered_questions
            WHERE question = :question
        """),
        {"question": question}
    ).fetchone()

    if existing:
        # incrementar ocurrencias
        db.execute(
            text("""
                UPDATE unanswered_questions
                SET occurrences = occurrences + 1
                WHERE id = :id
            """),
            {"id": existing.id}
        )
        db.commit()
        return

    # insertar nueva pregunta
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