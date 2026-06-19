from openai import AsyncOpenAI
from app.core.config import settings
from app.core.rate_limiter import RateLimiter
from app.services.usage_service import UsageService
from app.models.openai_usage import OpenAIUsage
from app.database.session import SessionLocal
from app.rag.prompt import SYSTEM_PROMPT

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
rate_limiter = RateLimiter(max_calls=8, period=1.0)


class LLMService:

    async def generate(
        self,
        user_prompt: str,
        user_id: str | None = None,
        endpoint: str | None = None
    ) -> dict:

        await rate_limiter.acquire()

        try:
            response = await client.chat.completions.create(
                model=settings.CHAT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI error: {str(e)}")

        message = response.choices[0].message.content.strip()

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        cost = UsageService.calculate_cost(
            settings.CHAT_MODEL,
            input_tokens,
            output_tokens
        )

        if user_id and endpoint:
            db = SessionLocal()
            try:
                usage_record = OpenAIUsage(
                    user_id=str(user_id),
                    endpoint=endpoint,
                    model=settings.CHAT_MODEL,
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    total_tokens=total_tokens,
                    estimated_cost=cost
                )
                db.add(usage_record)
                db.commit()
            finally:
                db.close()

        return {
            "text": message,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": cost
            }
        }