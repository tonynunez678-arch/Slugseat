import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from app.config import Settings

log = logging.getLogger("slugseat.mailer")


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


@dataclass
class ConsoleMailer:
    sent: list[Email] = field(default_factory=list)

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append(Email(to, subject, body))
        log.info("email to %s | %s\n%s", to, subject, body)


class SmtpMailer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.email_from or self.settings.smtp_user
        message["To"] = to
        message.set_content(body)
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if self.settings.smtp_user:
                smtp.login(self.settings.smtp_user, self.settings.smtp_password)
            smtp.send_message(message)
        log.info("sent email to %s | %s", to, subject)


def build_mailer(settings: Settings) -> Mailer:
    return SmtpMailer(settings) if settings.smtp_host else ConsoleMailer()
