from sqlalchemy.orm import Session
from app.rag.pipeline import RAGPipeline
# VERSION PRUEBA SERVIDOR 22-05-2026

class LangChainRAGWrapper:

    def __init__(
        self,
        conversation_id: int,
        role: str,
        segment: str | None,
        db: Session,
        state: dict | None = None
    ):
        self.conversation_id = conversation_id

        self.rag = RAGPipeline(
            role=role,
            segment=segment,
            db=db,
            state=state
        )

    async def ask(
        self,
        question: str,
        user_id: str | None = None,
        endpoint: str | None = None,
        chat_history: list | None = None
    ) -> dict:

        result = await self.rag.ask(
            question=question,
            conversation_id=self.conversation_id,
            user_id=user_id,
            endpoint=endpoint,
            chat_history=chat_history
        )

        # Garantizar que siempre venga source
        return {
            "text": result.get("text", ""),
            "source": result.get("source", "rag"),
            "debug": result.get("debug")
        }