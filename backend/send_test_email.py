import sys

from app.config import get_settings
from app.mailer import ConsoleMailer, build_mailer


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python send_test_email.py you@ucsc.edu")
        sys.exit(1)
    settings = get_settings()
    mailer = build_mailer(settings)
    if isinstance(mailer, ConsoleMailer):
        print("No email service is set up. Add SLUGSEAT_BREVO_API_KEY or the SMTP settings to backend/.env first.")
        sys.exit(1)
    mailer.send(sys.argv[1], "SlugSeat test email", "If you can read this, SlugSeat can send email.")
    print(f"Sent a test email to {sys.argv[1]} from {settings.email_from or settings.smtp_user} using {type(mailer).__name__}.")


if __name__ == "__main__":
    main()
