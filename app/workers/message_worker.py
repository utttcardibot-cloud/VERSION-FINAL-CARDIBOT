import json
import pika
import os
import time
from datetime import datetime

from app.database.session import SessionLocal
from app.models.conversation import Conversation
from app.models.message import Message


# =========================
# CONSTRUIR URL DESDE .ENV
# =========================

RABBIT_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBIT_USER = os.getenv("RABBITMQ_USER", "admin")
RABBIT_PASS = os.getenv("RABBITMQ_PASS", "admin123")

RABBIT_URL = f"amqp://{RABBIT_USER}:{RABBIT_PASS}@{RABBIT_HOST}:5672/"

QUEUE_NAME = "message_persistence"


def callback(ch, method, properties, body):

    db = SessionLocal()

    try:
        data = json.loads(body)

        conversation = None

        if data.get("conversation_id"):
            conversation = db.query(Conversation).filter(
                Conversation.id == data["conversation_id"]
            ).first()

        if not conversation:
            conversation = Conversation(
                title="Nueva conversación",
                created_at=datetime.utcnow(),
                state={}
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)

        db.add(Message(
            conversation_id=conversation.id,
            role="user",
            content=data["question"],
            created_at=datetime.utcnow()
        ))

        db.add(Message(
            conversation_id=conversation.id,
            role="bot",
            content=data["answer"],
            created_at=datetime.utcnow()
        ))

        db.commit()

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print("❌ Error procesando mensaje:", e)
        db.rollback()
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    finally:
        db.close()


def connect_with_retry():

    while True:
        try:
            print(f"🔌 Conectando a RabbitMQ en {RABBIT_HOST}...")
            connection = pika.BlockingConnection(
                pika.URLParameters(RABBIT_URL)
            )
            print("✅ Conectado a RabbitMQ")
            return connection
        except Exception as e:
            print("⏳ Esperando RabbitMQ...", e)
            time.sleep(5)


def start_worker():

    connection = connect_with_retry()
    channel = connection.channel()

    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=10)

    channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=callback
    )

    print("🧠 Message Worker escuchando...")
    channel.start_consuming()


if __name__ == "__main__":
    start_worker()