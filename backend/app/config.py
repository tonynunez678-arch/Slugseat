from functools import lru_cache

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
    email_from: str = "alerts@slugseat.local"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
