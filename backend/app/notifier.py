import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.config import Settings

log = logging.getLogger("slugseat.notifier")


@dataclass(frozen=True)
class SeatAlert:
    email: str
    phone: str | None
    term: str
    class_number: str
    title: str
    seats_open: int

    @property
    def text(self) -> str:
        seats = "seat" if self.seats_open == 1 else "seats"
        return f"SlugSeat: {self.title} (#{self.class_number}) has {self.seats_open} open {seats}. Enroll now!"


class Notifier(Protocol):
    channel: str

    def send(self, alert: SeatAlert) -> None: ...


@dataclass
class ConsoleNotifier:
    channel: str = "console"
    sent: list[SeatAlert] = field(default_factory=list)

    def send(self, alert: SeatAlert) -> None:
        self.sent.append(alert)
        log.info("alert to %s: %s", alert.email, alert.text)


class EmailNotifier:
    channel = "email"

    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, alert: SeatAlert) -> None:
        message = EmailMessage()
        message["Subject"] = f"Seat open: {alert.title}"
        message["From"] = self.settings.email_from
        message["To"] = alert.email
        message.set_content(alert.text)
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as smtp:
            smtp.starttls()
            if self.settings.smtp_user:
                smtp.login(self.settings.smtp_user, self.settings.smtp_password)
            smtp.send_message(message)


class TwilioNotifier:
    channel = "sms"

    def __init__(self, settings: Settings, fallback: Notifier):
        self.settings = settings
        self.fallback = fallback

    def send(self, alert: SeatAlert) -> None:
        if not alert.phone:
            self.fallback.send(alert)
            return
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.settings.twilio_account_sid}/Messages.json"
        response = httpx.post(
            url,
            data={"From": self.settings.twilio_from_number, "To": alert.phone, "Body": alert.text},
            auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token),
            timeout=10,
        )
        response.raise_for_status()


def build_notifier(settings: Settings) -> Notifier:
    if settings.notifier == "email":
        return EmailNotifier(settings)
    if settings.notifier == "sms":
        return TwilioNotifier(settings, fallback=EmailNotifier(settings))
    return ConsoleNotifier()
