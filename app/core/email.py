import os
import smtplib
from email.message import EmailMessage
from datetime import datetime

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


# =========================
# VERIFICACIÓN DE CUENTA
# =========================
def send_verification_email(to_email: str, verification_link: str):
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    msg = EmailMessage()
    msg["Subject"] = "Verifica tu cuenta institucional | CardiBot UTTT"
    msg["From"] = SMTP_USER
    msg["To"] = to_email

    msg.set_content(f"""
Estimado(a) usuario,

Gracias por registrarte en CardiBot, la inteligencia artificial institucional
de la Universidad Tecnológica de Tula-Tepeji.

Para completar tu registro y activar tu cuenta institucional,
haz clic en el siguiente enlace de verificación:

{verification_link}

Este enlace es personal e intransferible.
Si tú no realizaste este registro, puedes ignorar este mensaje.

Fecha de solicitud: {fecha}

Atentamente,
Equipo CardiBot
Universidad Tecnológica de Tula-Tepeji
""")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


# =========================
# COMENTARIOS / FEEDBACK
# =========================
def send_feedback_email(
    message: str,
    user_email: str | None = None,
    is_anonymous: bool = False
):
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    msg = EmailMessage()
    msg["Subject"] = " Nuevo comentario - CardiBot UTTT"
    msg["From"] = SMTP_USER
    msg["To"] = "utttcardibot@gmail.com"

    sender = "Anónimo" if is_anonymous else (user_email or "Desconocido")

    msg.set_content(f"""
Nuevo comentario recibido en CardiBot

Usuario: {sender}

Comentario:
{message}

 Fecha: {fecha}
""")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
