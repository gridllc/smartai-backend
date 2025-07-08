from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from config import settings
from pydantic import EmailStr
from typing import List

# 1. Centralize the email configuration using the settings from config.py
conf = ConnectionConfig(
    MAIL_USERNAME=settings.email_username,
    MAIL_PASSWORD=settings.email_password,
    MAIL_FROM=settings.email_username,
    MAIL_PORT=settings.email_port,
    MAIL_SERVER=settings.email_host,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

# 2. Create a single, reusable function to send emails


async def send_email(recipients: List[EmailStr], subject: str, body: str):
    """
    Sends an HTML email to a list of recipients.
    """
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=body,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)
    print(f"Email sent to {recipients} with subject: '{subject}'")
