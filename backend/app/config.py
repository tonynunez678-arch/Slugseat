import os
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SLUGSEAT_", extra="ignore")

    database_url: str = "sqlite:///./slugseat.db"
    class_search_url: str = "https://pisa.ucsc.edu/class_search/index.php"
    user_agent: str = "SlugSeat/0.1 (student project; opt-in seat alerts)"
    default_term: str = "2270"

    min_request_interval: float = 2.0
    cache_ttl_seconds: int = 60
    poll_interval_seconds: int = 60
    request_timeout_seconds: float = 15.0

    notifier: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    api_base_url: str = ""
    frontend_url: str = ""
    frontend_dist: str = ""
    run_poller: bool = False
    verify_token_ttl_hours: int = 24
    verify_resend_seconds: int = 300

    cors_origins: list[str] = ["http://localhost:5173"]


    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @model_validator(mode="after")
    def fill_public_urls(self) -> "Settings":
        public_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
        if public_url:
            self.api_base_url = self.api_base_url or public_url
            self.frontend_url = self.frontend_url or public_url
        self.api_base_url = self.api_base_url or "http://localhost:8000"
        self.frontend_url = self.frontend_url or "http://localhost:5173"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
