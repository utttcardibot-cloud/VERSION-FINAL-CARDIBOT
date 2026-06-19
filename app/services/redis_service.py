import os
import time
import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    max_connections=100,
    decode_responses=True
)

def connect_redis(retries=10):

    for attempt in range(retries):
        try:
            print(f"🔴 Conectando a Redis en {REDIS_HOST}:{REDIS_PORT}...")

            client = redis.Redis(
                connection_pool=pool,
                socket_timeout=2,
                socket_connect_timeout=2
            )

            client.ping()

            print("✅ Conectado a Redis")
            return client

        except Exception as e:
            print("⏳ Esperando Redis...", e)
            time.sleep(3)

    raise RuntimeError("No se pudo conectar a Redis")

redis_client = connect_redis()