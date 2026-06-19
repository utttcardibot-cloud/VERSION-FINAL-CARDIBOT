import os
import json
import pika
import logging

logger = logging.getLogger(__name__)

RABBIT_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBIT_USER = os.getenv("RABBITMQ_USER", "admin")
RABBIT_PASS = os.getenv("RABBITMQ_PASS", "admin123")

QUEUE = "embedding_queue"


def publish_embedding_task(chunk_id: str, text: str):

    try:
        credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)

        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=RABBIT_HOST,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300,
                connection_attempts=3,
                retry_delay=3,
            )
        )

        channel = connection.channel()

        # Cola durable
        channel.queue_declare(
            queue=QUEUE,
            durable=True
        )

        message = {
            "chunk_id": chunk_id,
            "text": text
        }

        channel.basic_publish(
            exchange="",
            routing_key=QUEUE,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # mensaje persistente
                content_type="application/json"
            )
        )

        connection.close()

        logger.info(f"Chunk enviado a Rabbit: {chunk_id}")

    except Exception as e:
        logger.exception("Error enviando chunk a RabbitMQ")
        raise