import hashlib
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from statistics import median

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session, init_db
from app.mailer import Mailer, build_mailer
from app.models import Alert, ClassSnapshot, User, Watch, utcnow
from app.schemas import ClassStatus, Metrics, Term, WatchCreate, WatchOut
from app.scraper import term_code


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    settings = get_settings()
    stop = threading.Event()
    thread = None
    if settings.run_poller:
        from app.poller import start_background

        thread = start_background(settings, stop)
    yield
    stop.set()
    if thread:
        thread.join(timeout=5)


app = FastAPI(title="SlugSeat", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache
def get_mailer() -> Mailer:
    return build_mailer(get_settings())


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _watch_out(session: Session, watch: Watch) -> WatchOut:
    snapshot = session.get(ClassSnapshot, (watch.term, watch.class_number))
    status = None
    if snapshot:
        status = ClassStatus(
            title=snapshot.title,
            status=snapshot.status,
            enrolled=snapshot.enrolled,
            capacity=snapshot.capacity,
            seats_open=snapshot.seats_open,
            checked_at=snapshot.checked_at,
        )
    return WatchOut(
        id=watch.id,
        term=watch.term,
        subject=watch.subject,
        catalog_number=watch.catalog_number,
        class_number=watch.class_number,
        active=watch.active,
        email_verified=watch.user.verified,
        created_at=watch.created_at,
        class_status=status,
    )


def _start_verification(user: User, settings: Settings) -> tuple[str, str, str] | None:
    now = utcnow()
    if user.verify_sent_at and now - _aware(user.verify_sent_at) < timedelta(seconds=settings.verify_resend_seconds):
        return None
    token = secrets.token_urlsafe(32)
    user.verify_token_hash = hash_token(token)
    user.verify_sent_at = now
    link = f"{settings.api_base_url}/api/verify?token={token}"
    body = (
        "Thanks for signing up for SlugSeat.\n\n"
        f"Confirm your email to start getting seat alerts:\n{link}\n\n"
        f"This link expires in {settings.verify_token_ttl_hours} hours. "
        "If you didn't sign up, you can ignore this email and you won't hear from us.\n"
    )
    return user.email, "Confirm your SlugSeat email", body


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/terms", response_model=list[Term])
def terms(today: date | None = None) -> list[Term]:
    today = today or date.today()
    quarters = ["winter", "spring", "summer", "fall"]
    result = []
    for year in (today.year, today.year + 1):
        for quarter in quarters:
            result.append(Term(code=term_code(year, quarter), name=f"{year} {quarter.title()}"))
    current = (today.month - 1) // 3
    return result[current : current + 4]


@app.post("/api/watches", response_model=WatchOut, status_code=201)
def create_watch(
    payload: WatchCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    mailer: Mailer = Depends(get_mailer),
    settings: Settings = Depends(get_settings),
) -> WatchOut:
    email = payload.email.lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, phone=payload.phone)
        session.add(user)
        session.flush()
    elif payload.phone:
        user.phone = payload.phone
    watch = session.scalar(
        select(Watch).where(Watch.user_id == user.id, Watch.term == payload.term, Watch.class_number == payload.class_number)
    )
    if watch is None:
        watch = Watch(
            user_id=user.id,
            term=payload.term,
            subject=payload.subject,
            catalog_number=payload.catalog_number,
            class_number=payload.class_number,
        )
        session.add(watch)
    else:
        watch.subject = payload.subject
        watch.catalog_number = payload.catalog_number
        watch.active = True
        watch.notified_open = False
    verification = None if user.verified else _start_verification(user, settings)
    session.commit()
    session.refresh(watch)
    if verification:
        background.add_task(mailer.send, *verification)
    return _watch_out(session, watch)


@app.get("/api/verify")
def verify(token: str, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> RedirectResponse:
    user = session.scalar(select(User).where(User.verify_token_hash == hash_token(token)))
    expired = user is not None and (
        user.verify_sent_at is None
        or utcnow() - _aware(user.verify_sent_at) > timedelta(hours=settings.verify_token_ttl_hours)
    )
    if user is None or expired:
        return RedirectResponse(f"{settings.frontend_url}/?verified=0", status_code=303)
    user.verified = True
    user.verify_token_hash = None
    session.commit()
    return RedirectResponse(f"{settings.frontend_url}/?verified=1", status_code=303)


@app.get("/api/watches", response_model=list[WatchOut])
def list_watches(email: str = Query(...), session: Session = Depends(get_session)) -> list[WatchOut]:
    user = session.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        return []
    return [_watch_out(session, w) for w in user.watches if w.active]


@app.delete("/api/watches/{watch_id}", status_code=204)
def delete_watch(watch_id: int, email: str = Query(...), session: Session = Depends(get_session)) -> None:
    watch = session.get(Watch, watch_id)
    if watch is None or watch.user.email != email.lower():
        raise HTTPException(status_code=404, detail="Watch not found")
    watch.active = False
    session.commit()


@app.get("/api/metrics", response_model=Metrics)
def metrics(session: Session = Depends(get_session)) -> Metrics:
    alerts = session.scalars(select(Alert)).all()
    latencies = [(_aware(a.sent_at) - _aware(a.detected_at)).total_seconds() for a in alerts]
    return Metrics(
        users=session.scalar(select(func.count(User.id))) or 0,
        verified_users=session.scalar(select(func.count(User.id)).where(User.verified)) or 0,
        active_watches=session.scalar(select(func.count(Watch.id)).where(Watch.active)) or 0,
        classes_tracked=session.scalar(select(func.count(ClassSnapshot.class_number))) or 0,
        alerts_sent=len(alerts),
        median_alert_latency_seconds=median(latencies) if latencies else None,
    )


def mount_frontend(target: FastAPI, dist: str) -> None:
    if dist and Path(dist).is_dir():
        target.mount("/", StaticFiles(directory=dist, html=True), name="frontend")


mount_frontend(app, get_settings().frontend_dist)
