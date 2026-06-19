from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import case, text
from openai import OpenAI
from sqlalchemy import text as sql_text
from typing import Optional
from app.database.session import SessionLocal
from app.models.faq import FAQ
client = OpenAI()

router = APIRouter(
    prefix="/faqs",
    tags=["faqs"]
)

# =====================================================
# DATABASE DEPENDENCY
# =====================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================
# GET ACTIVE FAQs
# =====================================================
@router.get("/active")
def get_active_faqs(category: str | None = Query(None), db: Session = Depends(get_db)):

    priority_order = case(
        (FAQ.id == 127, 1),
        (FAQ.id == 2, 2),
        (FAQ.id == 16, 3),
        (FAQ.id == 52, 4),
        (FAQ.id == 15, 5),
        (FAQ.id == 18, 6),
        (FAQ.id == 11, 7),
        else_=8
    )

    query = db.query(
        FAQ.id,
        FAQ.question,
        FAQ.category,
        FAQ.answer,
        FAQ.is_active
    ).filter(FAQ.is_active.is_(True))

    if category:
        query = query.filter(FAQ.category == category)

    faqs = query.order_by(priority_order, FAQ.id).all()

    return [
        {
            "id": faq.id,
            "question": faq.question,
            "category": faq.category,
            "answer": faq.answer,
            "is_active": faq.is_active
        }
        for faq in faqs
    ]


@router.get("")
def list_faqs(
    rol: Optional[str] = Query(None),
    unidadOrganica: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db)
):

    query = db.query(FAQ).filter(FAQ.is_active.is_(True))

    # =============================
    # FILTROS (IGUAL QUE DOCUMENTS)
    # =============================
    if rol == "SuperAdministrador":
        pass

    elif unidadOrganica:
        query = query.filter(
            FAQ.unidadorganica == unidadOrganica
        )

    else:
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "data": []
        }

    # =============================
    # TOTAL
    # =============================
    total = query.count()

    # =============================
    # PAGINACIÓN
    # =============================
    offset = (page - 1) * page_size

    faqs = (
        query
        .order_by(FAQ.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # =============================
    # RESPONSE
    # =============================
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "data": [
            {
                "id": faq.id,
                "question": faq.question,
                "answer": faq.answer,
                "category": faq.category,
                "nombre": faq.nombre,
                "puesto": faq.puesto,

                "unidadOrganica": faq.unidadorganica,
                "is_active": faq.is_active
            }
            for faq in faqs
        ]
    }

# =====================================================
# GET INACTIVE FAQs
# =====================================================

@router.get("/inactive")
def get_inactive_faqs(
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db)
):

    query = db.query(FAQ).filter(FAQ.is_active.is_(False))

    # =============================
    # FILTRO CATEGORY
    # =============================
    if category:
        query = query.filter(FAQ.category == category)

    # =============================
    # TOTAL
    # =============================
    total = query.count()

    # =============================
    # PAGINACIÓN
    # =============================
    offset = (page - 1) * page_size

    faqs = (
        query
        .order_by(FAQ.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # =============================
    # RESPONSE
    # =============================
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "data": [
            {
                "id": faq.id,
                "question": faq.question,
                "answer": faq.answer,
                "category": faq.category,
                "is_active": faq.is_active,

                # 🔥 CONTEXTO ORGANIZACIONAL
                "nombre": faq.nombre,
                "puesto": faq.puesto,
                "unidadOrganica": faq.unidadorganica
            }
            for faq in faqs
        ]
    }

# =====================================================
# GET CATEGORIES
# =====================================================

@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):

    categories = db.query(FAQ.category).distinct().all()

    return [c[0] for c in categories if c[0] is not None]


# =====================================================
# SEARCH FAQ
# =====================================================

@router.get("/search")
def search_faqs(q: str = Query(...), db: Session = Depends(get_db)):

    faqs = db.query(FAQ).filter(
        FAQ.question.ilike(f"%{q}%")
    ).all()

    return [
        {
            "id": faq.id,
            "question": faq.question,
            "category": faq.category,
            "answer": faq.answer,
            "is_active": faq.is_active
        }
        for faq in faqs
    ]


# =====================================================
# UNANSWERED QUESTIONS
# =====================================================

@router.get("/unanswered")
def get_unanswered_questions(segment: str | None = Query(None), db: Session = Depends(get_db)):

    query = "SELECT * FROM unanswered_questions"
    params = {}

    if segment:
        query += " WHERE segment = :segment"
        params["segment"] = segment

    query += " ORDER BY occurrences DESC, created_at DESC"

    rows = db.execute(text(query), params).fetchall()

    return [dict(row._mapping) for row in rows]


# =====================================================
# TOP UNANSWERED QUESTIONS
# =====================================================

@router.get("/unanswered/top")
def get_top_unanswered(db: Session = Depends(get_db)):

    rows = db.execute(
        text("""
        SELECT *
        FROM unanswered_questions
        ORDER BY occurrences DESC
        """)
    ).fetchall()

    return [dict(row._mapping) for row in rows]


# =====================================================
# DELETE ALL UNANSWERED
# =====================================================

@router.delete("/unanswered/all")
def delete_all_unanswered(db: Session = Depends(get_db)):

    result = db.execute(
        text("DELETE FROM unanswered_questions")
    )

    db.commit()

    return {"deleted": result.rowcount}


# =====================================================
# DELETE ONE UNANSWERED
# =====================================================

@router.delete("/unanswered/{question_id}")
def delete_unanswered(question_id: int, db: Session = Depends(get_db)):

    result = db.execute(
        text("DELETE FROM unanswered_questions WHERE id = :id"),
        {"id": question_id}
    )

    db.commit()

    return {"deleted": result.rowcount}


# =====================================================
# CREATE FAQ
# =====================================================
@router.post("/")
async def create_faq(
    question: str,
    answer: str,
    category: str | None = None,
    is_active: bool = True,

    # nuevos campos
    nombre: str = "",
    puesto: str = "",
    unidadOrganica: str = "",

    db: Session = Depends(get_db),
):

    # =========================
    # VALIDACIÓN
    # =========================
    if not question or not answer:
        raise HTTPException(400, "Pregunta y respuesta son obligatorias")

    normalized_question = question.lower().strip()

    # evitar duplicados
    existing = db.query(FAQ).filter(
        FAQ.question.ilike(question)
    ).first()

    if existing:
        raise HTTPException(400, "La FAQ ya existe")

    # =========================
    # GENERAR VARIANTES CON IA
    # =========================
    try:
        prompt = f"""
        Genera 5 variantes de la siguiente pregunta:

        {question}

        Reglas:
        - Español
        - Diferentes formas naturales de preguntar
        - Sin numeración
        - No repetir la misma frase
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres experto en NLP"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        ai_text = response.choices[0].message.content

        variants = [
            line.strip("- ").strip().lower()
            for line in ai_text.split("\n")
            if line.strip() and len(line.strip()) > 5
        ]

        # quitar duplicados + evitar repetir la original
        variants = list(set([
            v for v in variants
            if v != normalized_question
        ]))

        # fallback si IA devuelve vacío
        if not variants:
            variants = [normalized_question]

    except Exception:
        # fallback seguro si falla IA
        variants = [normalized_question]

    # =========================
    # CREAR FAQ
    # =========================
    new_faq = FAQ(
        question=question,
        answer=answer,
        category=category,
        is_active=is_active,

        variantes=variants,

        nombre=nombre,
        puesto=puesto,
        unidadorganica=unidadOrganica
    )

    db.add(new_faq)
    db.commit()
    db.refresh(new_faq)

    # =========================
    # LIMPIAR UNANSWERED
    # =========================
    db.execute(
        sql_text("""
        DELETE FROM unanswered_questions
        WHERE lower(question) = :question
        """),
        {"question": normalized_question}
    )
    db.commit()

    # =========================
    # RESPONSE
    # =========================
    return {
        "message": "FAQ creada correctamente",
        "id": new_faq.id,
        "question": new_faq.question,
        "variantes_generadas": variants,
        "categoria": category,
        "unidadOrganica": unidadOrganica
    }
# =====================================================
# UPDATE FAQ
# =====================================================

@router.put("/{faq_id}")
def update_faq(
    faq_id: int,
    unidadOrganica: str = Query(...),  # 🔥 obligatorio
    question: str | None = None,
    answer: str | None = None,
    category: str | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
):

    # =============================
    # BUSCAR CON SEGURIDAD
    # =============================
    faq = db.query(FAQ).filter(
        FAQ.id == faq_id,
        FAQ.unidadorganica == unidadOrganica
    ).first()

    if not faq:
        raise HTTPException(
            404,
            "FAQ no encontrada o no pertenece a tu unidad"
        )

    # =============================
    # UPDATE
    # =============================
    if question is not None:
        faq.question = question

    if answer is not None:
        faq.answer = answer

    if category is not None:
        faq.category = category

    if is_active is not None:
        faq.is_active = is_active

    db.commit()

    return {
        "message": "FAQ actualizada correctamente",
        "id": faq.id,
        "unidadOrganica": faq.unidadorganica
    }

# =====================================================
# REACTIVATE FAQ
# =====================================================

@router.patch("/{faq_id}/reactivate")
def reactivate_faq(faq_id: int, db: Session = Depends(get_db)):

    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()

    if not faq:
        raise HTTPException(404, "FAQ no encontrada")

    faq.is_active = True
    db.commit()

    return {"message": "FAQ reactivada", "id": faq.id}


# =====================================================
# DELETE FAQ
# =====================================================

@router.delete("/{faq_id}")
def delete_faq(faq_id: int, db: Session = Depends(get_db)):

    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()

    if not faq:
        raise HTTPException(404, "FAQ no encontrada")

    db.delete(faq)
    db.commit()

    return {"message": "FAQ eliminada correctamente"}


# =====================================================
# GET FAQ BY ID 
# =====================================================

@router.get("/{faq_id}")
def get_faq_by_id(faq_id: int, db: Session = Depends(get_db)):

    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()

    if not faq:
        raise HTTPException(404, "FAQ no encontrada")

    return {
        "id": faq.id,
        "question": faq.question,
        "answer": faq.answer,
        "category": faq.category,
        "is_active": faq.is_active
    }