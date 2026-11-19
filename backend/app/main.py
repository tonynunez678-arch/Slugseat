from contextlib import asynccontextmanager
from datetime import date
from statistics import median

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session, init_db
from app.models import Alert, ClassSnapshot, User, Watch
from app.schemas import ClassStatus, Metrics, Term, WatchCreate, WatchOut
from app.scraper import term_code


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="SlugSeat", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        created_at=watch.created_at,
        class_status=status,
    )


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
def create_watch(payload: WatchCreate, session: Session = Depends(get_session)) -> WatchOut:
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
    session.commit()
    return _watch_out(session, watch)


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
    latencies = [(a.sent_at - a.detected_at).total_seconds() for a in alerts]
    return Metrics(
        users=session.scalar(select(func.count(User.id))) or 0,
        active_watches=session.scalar(select(func.count(Watch.id)).where(Watch.active)) or 0,
        classes_tracked=session.scalar(select(func.count(ClassSnapshot.class_number))) or 0,
        alerts_sent=len(alerts),
        median_alert_latency_seconds=median(latencies) if latencies else None,
    )
