from langchain.memory import ConversationBufferMemory
from app.models.message import Message
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

# VERSION PRUEBA SERVIDOR 22-05-2026
class DatabaseConversationMemory:

    def __init__(self, conversation_id: str, db: Session):
        self.conversation_id = conversation_id
        self.db = db

        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )

        self._load_history()

    # =========================
    # CARGAR HISTORIAL DESDE DB
    # =========================
    def _load_history(self):
        try:
            messages = (
                self.db.query(Message)
                .filter(Message.conversation_id == self.conversation_id)
                .order_by(Message.created_at.asc())
                .all()
            )

            for msg in messages:
                if msg.role == "user":
                    self.memory.chat_memory.add_user_message(msg.content)
                elif msg.role == "bot":
                    self.memory.chat_memory.add_ai_message(msg.content)

        except Exception:
            logger.exception("Error cargando historial de conversación")
            raise

    # =========================
    # GUARDAR SOLO EN MEMORIA
    # (Persistencia real la hace el endpoint)
    # =========================
    def save(self, user_text: str, bot_text: str):
        self.memory.chat_memory.add_user_message(user_text)
        self.memory.chat_memory.add_ai_message(bot_text)
