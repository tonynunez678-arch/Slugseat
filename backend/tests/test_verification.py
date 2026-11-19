import re
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from app.main import hash_token
from app.models import User, utcnow
from app.notifier import EmailNotifier, SeatAlert

WATCH = {"email": "slug@ucsc.edu", "term": "2270", "subject": "CSE", "catalog_number": "114A", "class_number": "30628"}


def token_from(mailer) -> str:
    link = re.search(r"https?://\S+", mailer.sent[-1].body).group(0)
    return parse_qs(urlparse(link).query)["token"][0]


def test_signup_sends_confirmation_email(client, mailer):
    body = client.post("/api/watches", json=WATCH).json()
    assert body["email_verified"] is False
    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == "slug@ucsc.edu"
    assert "/api/verify?token=" in mailer.sent[0].body


def test_token_is_stored_hashed(client, mailer, session_factory):
    client.post("/api/watches", json=WATCH)
    token = token_from(mailer)
    with session_factory() as session:
        user = session.query(User).one()
        assert user.verify_token_hash == hash_token(token)
        assert token not in user.verify_token_hash


def test_confirm_link_verifies_user(client, mailer):
    client.post("/api/watches", json=WATCH)
    response = client.get("/api/verify", params={"token": token_from(mailer)}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/?verified=1")
    watches = client.get("/api/watches", params={"email": "slug@ucsc.edu"}).json()
    assert watches[0]["email_verified"] is True


def test_confirm_link_works_only_once(client, mailer):
    client.post("/api/watches", json=WATCH)
    token = token_from(mailer)
    client.get("/api/verify", params={"token": token}, follow_redirects=False)
    again = client.get("/api/verify", params={"token": token}, follow_redirects=False)
    assert again.headers["location"].endswith("/?verified=0")


def test_bad_token_is_rejected(client):
    response = client.get("/api/verify", params={"token": "nope"}, follow_redirects=False)
    assert response.headers["location"].endswith("/?verified=0")


def test_expired_token_is_rejected(client, mailer, session_factory):
    client.post("/api/watches", json=WATCH)
    with session_factory() as session:
        user = session.query(User).one()
        user.verify_sent_at = utcnow() - timedelta(hours=25)
        session.commit()
    response = client.get("/api/verify", params={"token": token_from(mailer)}, follow_redirects=False)
    assert response.headers["location"].endswith("/?verified=0")


def test_confirmation_email_is_not_resent_within_five_minutes(client, mailer):
    client.post("/api/watches", json=WATCH)
    client.post("/api/watches", json={**WATCH, "class_number": "30621"})
    assert len(mailer.sent) == 1


def test_verified_user_gets_no_more_confirmation_emails(client, mailer):
    client.post("/api/watches", json=WATCH)
    client.get("/api/verify", params={"token": token_from(mailer)}, follow_redirects=False)
    client.post("/api/watches", json={**WATCH, "class_number": "30621"})
    assert len(mailer.sent) == 1


def test_email_notifier_sends_alert(mailer):
    alert = SeatAlert("slug@ucsc.edu", None, "2270", "30628", "CSE 114A - 01 Found of Program Lang", 3)
    EmailNotifier(mailer, "http://localhost:5173").send(alert)
    sent = mailer.sent[0]
    assert sent.to == "slug@ucsc.edu"
    assert sent.subject == "Seat open: CSE 114A - 01 Found of Program Lang"
    assert "3 open seats" in sent.body


def test_smtp_mailer_logs_in_and_sends(monkeypatch):
    from app.config import Settings
    from app import mailer as mailer_module

    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["To"], message["From"], message["Subject"]))

    monkeypatch.setattr(mailer_module.smtplib, "SMTP", FakeSMTP)
    settings = Settings(_env_file=None, smtp_host="smtp.gmail.com", smtp_port=587, smtp_user="me@gmail.com", smtp_password="app-pass", email_from="")
    mailer_module.build_mailer(settings).send("slug@ucsc.edu", "Hi", "Body")
    assert calls == [
        ("connect", "smtp.gmail.com", 587),
        ("starttls",),
        ("login", "me@gmail.com", "app-pass"),
        ("send", "slug@ucsc.edu", "me@gmail.com", "Hi"),
    ]


def test_brevo_mailer_posts_to_api():
    import httpx

    from app.config import Settings
    from app.mailer import BrevoMailer, build_mailer

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"messageId": "abc"})

    settings = Settings(_env_file=None, brevo_api_key="key-123", email_from="me@gmail.com", smtp_host="smtp.gmail.com")
    assert isinstance(build_mailer(settings), BrevoMailer)
    BrevoMailer(settings, client=httpx.Client(transport=httpx.MockTransport(handler))).send("slug@ucsc.edu", "Hi", "Body")
    request = seen[0]
    assert str(request.url) == "https://api.brevo.com/v3/smtp/email"
    assert request.headers["api-key"] == "key-123"
    payload = __import__("json").loads(request.content)
    assert payload["sender"] == {"email": "me@gmail.com", "name": "SlugSeat"}
    assert payload["to"] == [{"email": "slug@ucsc.edu"}]
    assert payload["textContent"] == "Body"


def test_brevo_errors_are_raised():
    import httpx
    import pytest

    from app.config import Settings
    from app.mailer import BrevoMailer

    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"message": "Key not found"})))
    mailer = BrevoMailer(Settings(_env_file=None, brevo_api_key="bad", email_from="me@gmail.com"), client=client)
    with pytest.raises(RuntimeError, match="401"):
        mailer.send("slug@ucsc.edu", "Hi", "Body")
