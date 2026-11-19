import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import mount_frontend
from app.poller import PollStats, run_loop


def make_settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_render_database_url_uses_psycopg():
    assert make_settings(database_url="postgres://u:p@host/db").database_url == "postgresql+psycopg://u:p@host/db"
    assert make_settings(database_url="postgresql://u:p@host/db").database_url == "postgresql+psycopg://u:p@host/db"
    assert make_settings(database_url="sqlite:///./x.db").database_url == "sqlite:///./x.db"


def test_public_urls_default_to_localhost(monkeypatch):
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    settings = make_settings()
    assert settings.api_base_url == "http://localhost:8000"
    assert settings.frontend_url == "http://localhost:5173"


def test_public_urls_come_from_render(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://slugseat.onrender.com/")
    settings = make_settings()
    assert settings.api_base_url == "https://slugseat.onrender.com"
    assert settings.frontend_url == "https://slugseat.onrender.com"


def test_frontend_is_served_next_to_api(tmp_path):
    (tmp_path / "index.html").write_text("<h1>SlugSeat</h1>")
    target = FastAPI()

    @target.get("/api/health")
    def health():
        return {"status": "ok"}

    mount_frontend(target, str(tmp_path))
    client = TestClient(target)
    assert "SlugSeat" in client.get("/").text
    assert "SlugSeat" in client.get("/?verified=1").text
    assert client.get("/api/health").json() == {"status": "ok"}


def test_missing_frontend_dist_is_ignored(tmp_path):
    target = FastAPI()
    mount_frontend(target, str(tmp_path / "missing"))
    assert target.routes == [r for r in target.routes if getattr(r, "name", "") != "frontend"]


def test_run_loop_stops_when_asked():
    stop = threading.Event()
    runs = []

    class FakePoller:
        def run_once(self):
            runs.append(1)
            stop.set()
            return PollStats()

    run_loop(FakePoller(), 60, stop)
    assert runs == [1]
