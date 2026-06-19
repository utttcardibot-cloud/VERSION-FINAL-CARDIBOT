from fastapi import APIRouter, UploadFile, File, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
import re
import logging

from app.database.session import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.ingestion import IngestionService
from app.services.chunking import ChunkingService
from app.services.rabbitmq_service import publish_embedding_task

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

ingestion = IngestionService()
chunker = ChunkingService()

MAX_FILE_SIZE_MB = 15
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_MIME_TYPE = "application/pdf"
ALLOWED_EXTENSION = ".pdf"
ALLOWED_CATEGORIES = ["alumnos", "aspirantes", "padres"]


# ============================================================
# DB SESSION
# ============================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# UTILIDADES
# ============================================================

def sanitize_filename(filename: str) -> str:
    filename = filename.replace("\x00", "")
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)


def validate_uuid(id_str: str):
    try:
        uuid.UUID(id_str)
    except ValueError:
        raise HTTPException(400, "UUID inválido")


# ============================================================
# LISTAR DOCUMENTOS
# ============================================================

from typing import Optional
from fastapi import Query

@router.get("")
def list_documents(
    rol: Optional[str] = Query(None),
    unidadOrganica: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db)
):

    query = db.query(Document)

    # =============================
    # FILTROS
    # =============================

    if rol == "SuperAdministrador":
        # ve todo
        pass

    elif unidadOrganica:
        query = query.filter(
            Document.unidad_organica == unidadOrganica
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

    documents = (
        query
        .order_by(Document.created_at.desc())
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
                "id": str(doc.id),
                "file_name": doc.file_name,
                "category": doc.category,
                "nombre": doc.nombre,
                "puesto": doc.puesto,
                "unidadOrganica": doc.unidad_organica,
                "created_at": doc.created_at
            }
            for doc in documents
        ]
    }
# ============================================================
# SUBIR DOCUMENTO (ENCOLADO A RABBIT)
# ============================================================
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Query(...),

    # 🔥 nuevos campos
    nombre: str = Query(...),
    puesto: str = Query(...),
    unidadOrganica: str = Query(...),

    db: Session = Depends(get_db)
):

    # =========================
    # VALIDACIONES
    # =========================
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(400, "Categoría inválida")

    if file.content_type != ALLOWED_MIME_TYPE:
        raise HTTPException(400, "Solo se permiten archivos PDF")

    if not file.filename.lower().endswith(ALLOWED_EXTENSION):
        raise HTTPException(400, "Extensión inválida")

    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(400, "Archivo demasiado grande")

    safe_filename = sanitize_filename(file.filename)

    # =========================
    # REEMPLAZO SI YA EXISTE
    # =========================
    existing = db.query(Document).filter(
        Document.file_name == safe_filename
    ).first()

    if existing:
        db.delete(existing)
        db.commit()

    try:
        # =========================
        # CREAR DOCUMENTO (FIX 🔥)
        # =========================
        document = Document(
            id=uuid.uuid4(),
            file_name=safe_filename,
            category=category,
            nombre=nombre,
            puesto=puesto,
            unidad_organica=unidadOrganica,  # ✅ FIX AQUÍ
            created_at=datetime.utcnow()
        )

        db.add(document)
        db.flush()

        # =========================
        # EXTRAER TEXTO
        # =========================
        sections = ingestion.extract_sections(file_bytes, safe_filename)

        if not sections:
            raise HTTPException(400, "PDF sin texto legible")

        total_text = " ".join(sec["content"] for sec in sections)

        if len(total_text.strip()) < 300:
            raise HTTPException(
                400,
                "Documento con contenido insuficiente o escaneado sin texto"
            )

        # =========================
        # CHUNKING
        # =========================
        structured_chunks = chunker.chunk_sections(sections)

        if not structured_chunks:
            raise HTTPException(400, "No se generaron chunks válidos")

        chunk_objects = []

        for idx, chunk in enumerate(structured_chunks):

            chunk_obj = DocumentChunk(
                id=uuid.uuid4(),
                document_id=document.id,
                file_name=safe_filename,
                chunk_index=idx,
                content=chunk["content"],
                embedding=None,
                status="pending",
                section_title=chunk.get("title"),
                section_index=chunk.get("section_index")
            )

            chunk_objects.append(chunk_obj)

        db.bulk_save_objects(chunk_objects)
        db.commit()

        # =========================
        # RABBITMQ
        # =========================
        for chunk_obj in chunk_objects:
            publish_embedding_task(
                str(chunk_obj.id),
                chunk_obj.content
            )

        logger.info(f"Documento encolado: {safe_filename}")
        logger.info(f"Chunks enviados a Rabbit: {len(chunk_objects)}")

        return {
            "message": "Documento recibido y encolado para procesamiento",
            "file": safe_filename,
            "category": category,
            "nombre": nombre,
            "puesto": puesto,
            "unidadOrganica": unidadOrganica,
            "total_chunks": len(chunk_objects)
        }

    except Exception as e:
        db.rollback()
        logger.exception("Error procesando documento")
        raise HTTPException(500, f"Error interno: {str(e)}")
# ============================================================
# ACTUALIZAR CATEGORÍA
# ============================================================

@router.put("/{document_id}")
def update_document_category(
    document_id: str,
    category: str = Query(...),
    db: Session = Depends(get_db)
):

    validate_uuid(document_id)

    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(400, "Categoría inválida")

    document = db.query(Document).filter(
        Document.id == document_id
    ).first()

    if not document:
        raise HTTPException(404, "Documento no encontrado")

    document.category = category
    db.commit()

    return {
        "message": "Categoría actualizada correctamente",
        "id": document_id,
        "new_category": category
    }


# ============================================================
# ELIMINAR DOCUMENTO
# ============================================================

@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    db: Session = Depends(get_db)
):

    validate_uuid(document_id)

    document = db.query(Document).filter(
        Document.id == document_id
    ).first()

    if not document:
        raise HTTPException(404, "Documento no encontrado")

    db.delete(document)
    db.commit()

    return {
        "message": "Documento eliminado correctamente",
        "id": document_id
    }