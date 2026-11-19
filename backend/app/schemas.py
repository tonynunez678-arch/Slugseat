from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class WatchCreate(BaseModel):
    email: EmailStr
    phone: str | None = Field(default=None, pattern=r"^\+\d{10,15}$")
    term: str = Field(pattern=r"^\d{4}$")
    class_number: str = Field(pattern=r"^\d{5}$")


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
