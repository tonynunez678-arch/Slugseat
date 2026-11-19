import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Alert, ClassSnapshot, User, Watch, utcnow
from app.notifier import Notifier, SeatAlert
from app.scraper import ClassInfo

log = logging.getLogger("slugseat.poller")


@dataclass
class PollStats:
    classes_checked: int = 0
    cache_hits: int = 0
    alerts_sent: int = 0
    errors: list[str] = field(default_factory=list)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Poller:
    def __init__(self, session_factory: sessionmaker, fetch, notifier: Notifier, cache_ttl_seconds: int = 60, now=utcnow):
        self.session_factory = session_factory
        self.fetch = fetch
        self.notifier = notifier
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self.now = now

    def watched_courses(self, session: Session) -> dict[tuple[str, str, str], set[str]]:
        rows = session.execute(
            select(Watch.term, Watch.subject, Watch.catalog_number, Watch.class_number)
            .join(User)
            .where(Watch.active, User.verified)
            .distinct()
        )
        courses: dict[tuple[str, str, str], set[str]] = {}
        for term, subject, catalog, number in rows:
            courses.setdefault((term, subject, catalog), set()).add(number)
        return dict(sorted(courses.items()))

    def run_once(self) -> PollStats:
        stats = PollStats()
        with self.session_factory() as session:
            for (term, subject, catalog), numbers in self.watched_courses(session).items():
                try:
                    self._check(session, term, subject, catalog, numbers, stats)
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    stats.errors.append(f"{term}/{subject} {catalog}: {exc}")
                    log.exception("failed checking %s/%s %s", term, subject, catalog)
        return stats

    def _is_fresh(self, snapshots: list[ClassSnapshot | None], now: datetime) -> bool:
        return all(s is not None and now - _aware(s.checked_at) < self.cache_ttl for s in snapshots)

    def _check(self, session: Session, term: str, subject: str, catalog: str, numbers: set[str], stats: PollStats) -> None:
        now = self.now()
        snapshots = {n: session.get(ClassSnapshot, (term, n)) for n in numbers}
        if self._is_fresh(list(snapshots.values()), now):
            stats.cache_hits += 1
            return
        results: list[ClassInfo] = self.fetch(term, subject, catalog)
        stats.classes_checked += 1
        by_number = {info.class_number: info for info in results}
        for number in sorted(numbers):
            info = by_number.get(number)
            if info is None:
                continue
            snapshot = snapshots[number]
            was_open = snapshot is not None and snapshot.seats_open > 0
            if snapshot is None:
                snapshot = ClassSnapshot(term=term, class_number=number)
                session.add(snapshot)
            snapshot.title = info.title
            snapshot.status = info.status
            snapshot.enrolled = info.enrolled
            snapshot.capacity = info.capacity
            snapshot.checked_at = now
            if info.seats_open > 0 and not was_open:
                snapshot.opened_at = now
            self._sync_watches(session, snapshot, stats)

    def _sync_watches(self, session: Session, snapshot: ClassSnapshot, stats: PollStats) -> None:
        watches = session.scalars(
            select(Watch).where(Watch.active, Watch.term == snapshot.term, Watch.class_number == snapshot.class_number)
        ).all()
        for watch in watches:
            if snapshot.seats_open == 0:
                watch.notified_open = False
                continue
            if watch.notified_open or not watch.user.verified:
                continue
            self.notifier.send(
                SeatAlert(
                    email=watch.user.email,
                    phone=watch.user.phone,
                    term=snapshot.term,
                    class_number=snapshot.class_number,
                    title=snapshot.title,
                    seats_open=snapshot.seats_open,
                )
            )
            watch.notified_open = True
            session.add(
                Alert(
                    watch_id=watch.id,
                    channel=self.notifier.channel,
                    seats_open=snapshot.seats_open,
                    detected_at=snapshot.opened_at or snapshot.checked_at,
                )
            )
            stats.alerts_sent += 1


def run_loop(poller: Poller, interval_seconds: float, stop: threading.Event, requests_made=lambda: 0) -> None:
    while not stop.is_set():
        started = time.monotonic()
        stats = poller.run_once()
        log.info(
            "poll done checked=%d cache_hits=%d alerts=%d errors=%d total_requests=%d",
            stats.classes_checked,
            stats.cache_hits,
            stats.alerts_sent,
            len(stats.errors),
            requests_made(),
        )
        stop.wait(max(interval_seconds - (time.monotonic() - started), 1))


def start_background(settings, stop: threading.Event) -> threading.Thread:
    from app.db import SessionLocal
    from app.notifier import build_notifier
    from app.scraper import ClassSearchClient, RateLimiter

    client = ClassSearchClient(
        settings.class_search_url,
        settings.user_agent,
        RateLimiter(settings.min_request_interval),
        timeout=settings.request_timeout_seconds,
    )
    poller = Poller(SessionLocal, client.fetch_course, build_notifier(settings), settings.cache_ttl_seconds)

    def target() -> None:
        try:
            run_loop(poller, settings.poll_interval_seconds, stop, lambda: client.requests_made)
        finally:
            client.close()

    thread = threading.Thread(target=target, name="slugseat-poller", daemon=True)
    thread.start()
    return thread


def main() -> None:
    from app.config import get_settings
    from app.db import init_db

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    init_db()
    stop = threading.Event()
    thread = start_background(settings, stop)
    try:
        while thread.is_alive():
            thread.join(1)
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
