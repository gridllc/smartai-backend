import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

EMAIL_USER = settings.email_username
EMAIL_PASS = settings.email_password
SMTP_SERVER = settings.smtp_server
SMTP_PORT = settings.smtp_port


def send_email_with_attachment(to_email, subject, body, file_path=None):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = to_email
    msg.set_content(body)

    if file_path:
        with open(file_path, "rb") as f:
            file_data = f.read()
            filename = os.path.basename(file_path)
            msg.add_attachment(file_data, maintype="application",
                               subtype="octet-stream", filename=filename)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_USER, EMAIL_PASS)
        smtp.send_message(msg)
