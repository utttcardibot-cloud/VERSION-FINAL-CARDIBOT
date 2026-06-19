from sqlalchemy.orm import Session
from app.models.faq import FAQ


def search_faqs(
    db: Session,
    query: str,
    limit: int = 5,
):
    """
    Búsqueda simple por texto (fase 1)
    """
    return (
        db.query(FAQ)
        .filter(
            FAQ.is_active == True,
            FAQ.question.ilike(f"%{query}%")
        )
        .limit(limit)
        .all()
    )
