# sends emails such as password reset codes
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("safarnama.mail")


def send(to: str, subject: str, body: str) -> bool:
    host = os.getenv("SMTP_HOST")
    if not host:
        log.warning("SMTP_HOST is not set, so this email was only written to the log. To %s: %s", to, body)
        return False
    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM", "Safarnama <no-reply@safarnama.app>")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
        smtp.starttls()
        if os.getenv("SMTP_USER"):
            smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(msg)
    return True
