from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    watches: Mapped[list["Watch"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Watch(Base):
    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("user_id", "term", "class_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    term: Mapped[str] = mapped_column(String(8))
    class_number: Mapped[str] = mapped_column(String(8))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notified_open: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="watches")


class ClassSnapshot(Base):
    __tablename__ = "class_snapshots"

    term: Mapped[str] = mapped_column(String(8), primary_key=True)
    class_number: Mapped[str] = mapped_column(String(8), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="")
    enrolled: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def seats_open(self) -> int:
        return max(self.capacity - self.enrolled, 0)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watches.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    seats_open: Mapped[int] = mapped_column(Integer)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
