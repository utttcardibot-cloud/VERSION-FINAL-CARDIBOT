import os
import json
import time
import asyncio
import traceback

import pika

from app.database.session import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import EmbeddingService

# =========================================
# CONFIG
# =========================================

RABBIT_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBIT_USER = os.getenv("RABBITMQ_USER", "admin")
RABBIT_PASS = os.getenv("RABBITMQ_PASS", "admin123")

QUEUE = "embedding_queue"

embedder = EmbeddingService()


# =========================================
# CONEXIÓN RABBIT
# =========================================

def connect():

    credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)

    parameters = pika.ConnectionParameters(
        host=RABBIT_HOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300,
        connection_attempts=5,
        retry_delay=5,
    )

    return pika.BlockingConnection(parameters)


# =========================================
# PROCESAMIENTO
# =========================================

def process_chunk(chunk_id: str, text: str):

    db = SessionLocal()

    try:
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id
        ).first()

        if not chunk:
            print(f"⚠ Chunk {chunk_id} no encontrado")
            return True  # ACK igual

        # Idempotencia
        if chunk.status == "processed":
            return True

        # 🔥 Usar tu servicio async correctamente
        embedding = asyncio.run(embedder.embed(text))

        chunk.embedding = embedding
        chunk.status = "processed"
        db.commit()

        print(f"✅ Chunk procesado {chunk_id}")

        return True

    except Exception as e:
        db.rollback()
        print("❌ Error procesando chunk:")
        traceback.print_exc()
        return False

    finally:
        db.close()


# =========================================
# CALLBACK RABBIT
# =========================================

def callback(ch, method, properties, body):

    try:
        data = json.loads(body)

        chunk_id = data["chunk_id"]
        text = data["text"]

        success = process_chunk(chunk_id, text)

        if success:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            # requeue = True → lo vuelve a intentar
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    except Exception:
        traceback.print_exc()
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


# =========================================
# START WORKER
# =========================================

def start_worker():

    while True:
        try:
            connection = connect()
            channel = connection.channel()

            channel.queue_declare(queue=QUEUE, durable=True)
            channel.basic_qos(prefetch_count=1)

            channel.basic_consume(
                queue=QUEUE,
                on_message_callback=callback
            )

            print("Worker escuchando embedding_queue...")
            channel.start_consuming()

        except Exception as e:
            print("⚠ Error conexión Rabbit. Reintentando en 5s...")
            time.sleep(5)


if __name__ == "__main__":
    start_worker()