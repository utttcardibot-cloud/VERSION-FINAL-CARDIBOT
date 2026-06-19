from app.database.session import engine
from app.database.session import Base

# 👇 IMPORTANTE: importar TODOS los modelos
from app.models.document_chunk import DocumentChunk
from app.models.user import User


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()