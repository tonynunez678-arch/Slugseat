import sys

from app.config import get_settings
from app.mailer import SmtpMailer


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python send_test_email.py you@ucsc.edu")
        sys.exit(1)
    settings = get_settings()
    if not settings.smtp_host:
        print("SLUGSEAT_SMTP_HOST is empty. Fill in the email settings in backend/.env first.")
        sys.exit(1)
    SmtpMailer(settings).send(sys.argv[1], "SlugSeat test email", "If you can read this, SlugSeat can send email.")
    print(f"Sent a test email to {sys.argv[1]} from {settings.email_from or settings.smtp_user}.")


if __name__ == "__main__":
    main()
