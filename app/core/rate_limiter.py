import asyncio
import time


class RateLimiter:
    """
    Rate limiter simple basado en ventana deslizante.
    Permite máximo `max_calls` en un período de `period` segundos.
    """

    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.monotonic()

            # Limpiar llamadas fuera de la ventana de tiempo
            self.calls = [
                call for call in self.calls
                if call > now - self.period
            ]

            # Si alcanzamos el límite, esperar
            if len(self.calls) >= self.max_calls:
                sleep_time = self.calls[0] + self.period - now
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                # Después de dormir, limpiar otra vez
                now = time.monotonic()
                self.calls = [
                    call for call in self.calls
                    if call > now - self.period
                ]

            # Registrar nueva llamada
            self.calls.append(time.monotonic())
