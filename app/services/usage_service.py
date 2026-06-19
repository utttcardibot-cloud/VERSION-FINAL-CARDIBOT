MODEL_PRICING = {
    "gpt-5-mini": {
        "input": 0.00000025,   # ⚠️ Ajusta al pricing real
        "output": 0.000001
    }
}


class UsageService:

    @staticmethod
    def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = MODEL_PRICING.get(model)

        if not pricing:
            return 0.0

        return round(
            input_tokens * pricing["input"] +
            output_tokens * pricing["output"],
            6
        )
