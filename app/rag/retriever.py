from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services.embedding_service import EmbeddingService
import hashlib
import time
import re
import unicodedata
import asyncio

# VERSION PRUEBA SERVIDOR 22-05-2026


embedder = EmbeddingService()


# =====================================================
# TEXT NORMALIZATION
# =====================================================
def normalize_text(text: str):

    text = text.lower().strip()

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")

    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    filler_words = {
        "ey", "oye", "hola", "bro", "porfa",
        "porfavor", "buenas", "buenos", "dias",
        "tardes", "noches"
    }

    words = text.split()
    words = [w for w in words if w not in filler_words]

    return " ".join(words)


# =====================================================
# QUERY EXPANSION
# =====================================================
def expand_query(query: str):

    tokens = query.split()

    if len(tokens) <= 2:
        expansions = [
            query,
            f"uttt {query}",
            f"universidad tecnologica tula tepeji {query}",
            f"carrera {query}",
            f"ingenieria {query}"
        ]
        return " ".join(expansions)

    return query


# =====================================================
# RETRIEVER
# =====================================================
class Retriever:

    _embedding_cache: dict[str, list[float]] = {}
    _cache_ttl: dict[str, float] = {}
    _CACHE_EXPIRATION = 600


    # =====================================================
    # INTENT MATCH
    # =====================================================
    async def search_intent(self, query_clean: str, db: Session, category: str | None):

        sql = """
        SELECT f.answer
        FROM faqs f
        WHERE f.is_active = true
        AND (:category IS NULL OR f.category = :category)
        AND (
            unaccent(lower(f.question)) = unaccent(lower(:q))
            OR EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(COALESCE(f.variantes,'[]')) v
                WHERE unaccent(lower(v)) = unaccent(lower(:q))
            )
        )
        LIMIT 1
        """

        return db.execute(text(sql), {
            "q": query_clean,
            "category": category
        }).fetchone()


    # =====================================================
    # FAQ SEARCH
    # =====================================================
    async def search_faq(self, query_clean: str, db: Session, category: str | None):

        sql = """
        SELECT
            f.question,
            f.answer,

            GREATEST(
                similarity(unaccent(lower(f.question)), unaccent(lower(:q))),
                similarity(unaccent(lower(f.answer)), unaccent(lower(:q))),
                COALESCE((
                    SELECT MAX(similarity(unaccent(lower(v)), unaccent(lower(:q))))
                    FROM jsonb_array_elements_text(COALESCE(f.variantes,'[]')) v
                ),0)
            ) AS sim_score,

            (
                SELECT COUNT(*)
                FROM unnest(string_to_array(unaccent(lower(:q)), ' ')) AS term
                WHERE
                    unaccent(lower(f.question)) LIKE '%' || term || '%'
                    OR unaccent(lower(f.answer)) LIKE '%' || term || '%'
                    OR EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements_text(COALESCE(f.variantes,'[]')) v
                        WHERE unaccent(lower(v)) LIKE '%' || term || '%'
                    )
            ) AS keyword_hits

        FROM faqs f

        WHERE f.is_active = true
        AND (:category IS NULL OR f.category = :category)
        AND (
            unaccent(lower(f.question)) LIKE '%' || unaccent(lower(:q)) || '%'
            OR unaccent(lower(f.answer)) LIKE '%' || unaccent(lower(:q)) || '%'

            OR EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(COALESCE(f.variantes,'[]')) v
                WHERE unaccent(lower(v)) LIKE '%' || unaccent(lower(:q)) || '%'
            )

            OR similarity(unaccent(lower(f.question)), unaccent(lower(:q))) > 0.25
            OR similarity(unaccent(lower(f.answer)), unaccent(lower(:q))) > 0.25

            OR EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(COALESCE(f.variantes,'[]')) v
                WHERE similarity(unaccent(lower(v)), unaccent(lower(:q))) > 0.25
            )
        )

        ORDER BY keyword_hits DESC, sim_score DESC
        LIMIT 5
        """

        return db.execute(text(sql), {
            "q": query_clean,
            "category": category
        }).fetchall()


    # =====================================================
    # MAIN RETRIEVE
    # =====================================================
    async def retrieve(
        self,
        query: str,
        role: str,
        segment: str | None,
        db: Session,
        limit: int | None = None
    ) -> dict:

        query_clean = normalize_text(query)
        query_clean = expand_query(query_clean)

        now = time.time()

        # =========================
        # CATEGORY
        # =========================
        category = None

        if role == "student":
            category = "alumnos"
        elif role == "anonymous":
            category = segment

        # =========================
        # INTENT
        # =========================
        intent_row = await self.search_intent(query_clean, db, category)

        if intent_row:
            return {
                "chunks": [intent_row[0]],
                "source": "faq",
                "debug": {
                    "stage": "intent",
                    "category_used": category,
                    "fallback": False
                }
            }

        # =========================
        # EMBEDDING CACHE
        # =========================
        query_hash = hashlib.sha256(query_clean.encode()).hexdigest()

        embedding_task = None

        if (
            query_hash in self._embedding_cache
            and now < self._cache_ttl.get(query_hash, 0)
        ):
            embedding = self._embedding_cache[query_hash]
        else:
            embedding_task = asyncio.create_task(embedder.embed(query_clean))

        faq_task = asyncio.create_task(
            self.search_faq(query_clean, db, category)
        )

        if embedding_task:
            faq_rows, embedding = await asyncio.gather(
                faq_task,
                embedding_task
            )

            self._embedding_cache[query_hash] = embedding
            self._cache_ttl[query_hash] = now + self._CACHE_EXPIRATION
        else:
            faq_rows = await faq_task

        # =========================
        # FAQ RESULT + FALLBACK
        # =========================
        used_fallback = False

        if not faq_rows:
            faq_rows = await self.search_faq(query_clean, db, None)
            used_fallback = True

        if faq_rows:

            faq_chunks = []

            for row in faq_rows:
                question = row[0]
                answer = row[1]

                faq_chunks.append(
                    f"Pregunta frecuente: {question}\n"
                    f"Respuesta oficial: {answer}"
                )

            return {
                "chunks": faq_chunks,
                "source": "faq",
                "debug": {
                    "stage": "faq",
                    "category_used": category if not used_fallback else "ALL",
                    "fallback": used_fallback
                }
            }

        # =========================
        # VECTOR SEARCH
        # =========================
        base_limit = 25

        if limit:
            base_limit = max(limit, 25)

        if category is None:

            sql = """
            SELECT content,
                   embedding <=> CAST(:embedding AS vector) AS vector_score
            FROM document_chunks
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """

            params = {
                "embedding": embedding,
                "limit": base_limit
            }

        else:

            sql = """
            SELECT dc.content,
                   dc.embedding <=> CAST(:embedding AS vector) AS vector_score
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.category = :category
            ORDER BY dc.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """

            params = {
                "embedding": embedding,
                "limit": base_limit,
                "category": category
            }

        rows = db.execute(text(sql), params).fetchall()

        if not rows:
            return {
                "chunks": [],
                "source": "rag",
                "debug": {
                    "stage": "rag",
                    "category_used": category,
                    "fallback": True
                }
            }

        # =========================
        # HYBRID RERANK
        # =========================
        query_terms = re.findall(r"\w+", query_clean)

        scored_chunks = []

        for content, vector_score in rows:

            content_lower = content.lower()

            lexical_hits = sum(
                1 for term in query_terms
                if term in content_lower
            )

            hybrid_score = vector_score - (lexical_hits * 0.2)

            scored_chunks.append((hybrid_score, content))

        scored_chunks.sort(key=lambda x: x[0])

        final_limit = limit if limit else 5

        return {
            "chunks": [chunk for _, chunk in scored_chunks[:final_limit]],
            "source": "rag",
            "debug": {
                "stage": "rag",
                "category_used": category if category else "ALL",
                "fallback": False
            }
        }