from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import time

from app.database.session import engine, Base
from app import models

# =========================
# ROUTERS
# =========================
from app.api.ask import router as ask_router
from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.faqs import router as faqs_router
from app.api.documents import router as documents_router
from app.api import usage


app = FastAPI(
    title="CardiBot – RAG Service",
    version="1.0.0"
)


# =========================
# STARTUP - DB INIT
# =========================
@app.on_event("startup")
def on_startup():

    print("🔥 VERSION NUEVA DB INIT 🔥")

    # -------------------------
    # Esperar a PostgreSQL
    # -------------------------
    for i in range(10):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("PostgreSQL conectado")
            break
        except Exception:
            print("Esperando PostgreSQL...")
            time.sleep(3)
    else:
        raise Exception("No se pudo conectar a PostgreSQL")

    # -------------------------
    # Inicialización DB
    # -------------------------
    try:
        with engine.begin() as conn:

            locked = conn.execute(
                text("SELECT pg_try_advisory_lock(123456789);")
            ).scalar()

            if locked:

                print("Inicializando base de datos...")

                # =========================
                # EXTENSIONES
                # =========================
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

                print("Extensiones OK")

                # =========================
                # TABLAS
                # =========================
                Base.metadata.create_all(bind=conn)

                print("Tablas OK")

                # =========================
                # MIGRACIONES DOCUMENTS
                # =========================
                conn.execute(text("""
                ALTER TABLE documents ADD COLUMN IF NOT EXISTS nombre VARCHAR(255);
                """))

                conn.execute(text("""
                ALTER TABLE documents ADD COLUMN IF NOT EXISTS puesto VARCHAR(255);
                """))

                conn.execute(text("""
                ALTER TABLE documents ADD COLUMN IF NOT EXISTS unidadorganica VARCHAR(255);
                """))

                # =========================
                # MIGRACIONES FAQ
                # =========================
                conn.execute(text("""
                ALTER TABLE faqs DROP CONSTRAINT IF EXISTS fk_faq_target;
                """))

                conn.execute(text("""
                ALTER TABLE faqs DROP COLUMN IF EXISTS target_faq_id;
                """))

                conn.execute(text("""
                ALTER TABLE faqs DROP COLUMN IF EXISTS intent;
                """))

                conn.execute(text("""
                ALTER TABLE faqs ADD COLUMN IF NOT EXISTS variantes JSONB DEFAULT '[]'::jsonb;
                """))

                conn.execute(text("""
                ALTER TABLE faqs ADD COLUMN IF NOT EXISTS nombre VARCHAR(255);
                """))

                conn.execute(text("""
                ALTER TABLE faqs ADD COLUMN IF NOT EXISTS puesto VARCHAR(255);
                """))

                conn.execute(text("""
                ALTER TABLE faqs ADD COLUMN IF NOT EXISTS unidadorganica VARCHAR(255);
                """))

                print("Migraciones OK")

                # =========================
                # INDICES
                # =========================

                # VECTOR
                conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
                ON document_chunks USING hnsw (embedding vector_cosine_ops);
                """))

                conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_semantic_cache_embedding
                ON semantic_cache USING hnsw (embedding vector_cosine_ops);
                """))

                # FAQ
                conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_faqs_question_trgm
                ON faqs USING gin (question gin_trgm_ops);
                """))

                conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_faq_answer_trgm
                ON faqs USING gin (answer gin_trgm_ops);
                """))

                conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_faq_variantes_gin
                ON faqs USING gin (variantes);
                """))

                # UNANSWERED
                conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_unanswered_created
                ON unanswered_questions(created_at);
                """))

                conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_unanswered_question
                ON unanswered_questions(question);
                """))

                # OPTIONAL
                conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_documents_category
                ON documents(category);
                """))

                print("Índices OK")

                conn.execute(text("SELECT pg_advisory_unlock(123456789);"))

                print("✅ DB lista para producción")

            else:
                print("Otro contenedor ya inicializó la DB")

    except Exception as e:
        print("Error inicializando DB:", str(e))
        raise e


# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# ROUTERS
# =========================
app.include_router(auth_router)
app.include_router(ask_router)
app.include_router(conversations_router)
app.include_router(faqs_router)
app.include_router(documents_router)
app.include_router(usage.router)

# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {
        "service": "CardiBot RAG API",
        "status": "running",
        "version": "1.0.0"
    }

# =========================
# HEALTHCHECK
# =========================
@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy"}
        )