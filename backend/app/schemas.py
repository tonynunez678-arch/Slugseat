from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class WatchCreate(BaseModel):
    email: EmailStr
    phone: str | None = Field(default=None, pattern=r"^\+\d{10,15}$")
    term: str = Field(pattern=r"^\d{4}$")
    subject: str = Field(pattern=r"^[A-Z]{2,5}$")
    catalog_number: str = Field(pattern=r"^\d{1,3}[A-Z]{0,2}$")
    class_number: str = Field(pattern=r"^\d{5}$")

    @field_validator("subject", "catalog_number", mode="before")
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.strip().upper() if isinstance(value, str) else value


class ClassStatus(BaseModel):
    title: str
    status: str
    enrolled: int
    capacity: int
    seats_open: int
    checked_at: datetime


class WatchOut(BaseModel):
    id: int
    term: str
    subject: str
    catalog_number: str
    class_number: str
    active: bool
    created_at: datetime
    class_status: ClassStatus | None = None


class Term(BaseModel):
    code: str
    name: str


class Metrics(BaseModel):
    users: int
    active_watches: int
    classes_tracked: int
    alerts_sent: int
    median_alert_latency_seconds: float | None
