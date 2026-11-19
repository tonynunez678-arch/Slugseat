from datetime import datetime, timedelta, timezone

from app.models import Alert, User, Watch
from app.notifier import ConsoleNotifier
from app.poller import Poller
from app.scraper import ClassInfo


class FakeSearch:
    def __init__(self):
        self.enrolled = 40
        self.calls = 0

    def __call__(self, term, subject, catalog):
        self.calls += 1
        return [
            ClassInfo("21234", "CSE 101 - 01 Intro Data Struct&Alg", "Open", self.enrolled, 40),
            ClassInfo("21240", "CSE 101 - 02 Intro Data Struct&Alg", "Closed", 250, 250),
        ]


class Clock:
    def __init__(self):
        self.value = datetime(2026, 11, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def seed(session_factory, emails=("a@ucsc.edu",), number="21234", subject="CSE", catalog="101"):
    with session_factory() as session:
        for email in emails:
            user = User(email=email)
            session.add(user)
            session.flush()
            session.add(Watch(user_id=user.id, term="2270", subject=subject, catalog_number=catalog, class_number=number))
        session.commit()


def make_poller(session_factory, search, notifier, clock):
    return Poller(session_factory, search, notifier, cache_ttl_seconds=60, now=clock)


def test_alerts_once_when_seat_opens(session_factory):
    seed(session_factory, emails=("a@ucsc.edu", "b@ucsc.edu"))
    search, notifier, clock = FakeSearch(), ConsoleNotifier(), Clock()
    poller = make_poller(session_factory, search, notifier, clock)

    assert poller.run_once().alerts_sent == 0

    search.enrolled = 38
    clock.advance(61)
    stats = poller.run_once()
    assert stats.alerts_sent == 2
    assert sorted(a.email for a in notifier.sent) == ["a@ucsc.edu", "b@ucsc.edu"]
    assert notifier.sent[0].seats_open == 2

    clock.advance(61)
    assert poller.run_once().alerts_sent == 0
    assert len(notifier.sent) == 2


def test_realerts_after_class_fills_and_reopens(session_factory):
    seed(session_factory)
    search, notifier, clock = FakeSearch(), ConsoleNotifier(), Clock()
    poller = make_poller(session_factory, search, notifier, clock)

    search.enrolled = 39
    poller.run_once()
    search.enrolled = 40
    clock.advance(61)
    poller.run_once()
    search.enrolled = 39
    clock.advance(61)
    poller.run_once()
    assert len(notifier.sent) == 2


def test_cache_shares_one_request_per_class(session_factory):
    seed(session_factory, emails=("a@ucsc.edu", "b@ucsc.edu", "c@ucsc.edu"))
    search, clock = FakeSearch(), Clock()
    poller = make_poller(session_factory, search, ConsoleNotifier(), clock)

    poller.run_once()
    assert search.calls == 1
    clock.advance(30)
    stats = poller.run_once()
    assert stats.cache_hits == 1
    assert search.calls == 1


def test_one_request_covers_every_section_of_a_course(session_factory):
    seed(session_factory, emails=("a@ucsc.edu",), number="21234")
    seed(session_factory, emails=("b@ucsc.edu",), number="21240")
    search = FakeSearch()
    search.enrolled = 39
    notifier = ConsoleNotifier()
    make_poller(session_factory, search, notifier, Clock()).run_once()
    assert search.calls == 1
    assert [a.class_number for a in notifier.sent] == ["21234"]


def test_inactive_watches_are_skipped(session_factory):
    seed(session_factory)
    with session_factory() as session:
        session.query(Watch).update({Watch.active: False})
        session.commit()
    search = FakeSearch()
    make_poller(session_factory, search, ConsoleNotifier(), Clock()).run_once()
    assert search.calls == 0


def test_fetch_errors_are_isolated(session_factory):
    seed(session_factory, number="11111", subject="CSE", catalog="101")
    seed(session_factory, emails=("b@ucsc.edu",), number="22222", subject="MATH", catalog="19A")

    def search(term, subject, catalog):
        if subject == "CSE":
            raise RuntimeError("boom")
        return [ClassInfo("22222", "MATH 19A - 01 Calculus", "Open", 10, 40)]

    notifier = ConsoleNotifier()
    stats = make_poller(session_factory, search, notifier, Clock()).run_once()
    assert len(stats.errors) == 1
    assert [a.class_number for a in notifier.sent] == ["22222"]
    with session_factory() as session:
        assert session.query(Alert).count() == 1
