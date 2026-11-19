import re

import httpx
import pytest

from tests.conftest import FIXTURES
from app.scraper import ClassSearchClient, RateLimiter, parse_results, search_form, term_code


def test_parse_results(results_html):
    classes = parse_results(results_html)
    assert [c.class_number for c in classes] == ["21234", "21240"]
    first, second = classes
    assert first.title == "CSE 101 - 01 Intro Data Struct&Alg"
    assert first.status == "Open"
    assert (first.enrolled, first.capacity, first.seats_open) == (36, 40, 4)
    assert second.status == "Closed"
    assert second.seats_open == 0


def test_parse_results_empty():
    assert parse_results("<html><body>No classes found</body></html>") == []


def test_parse_real_no_matches_page():
    page = (FIXTURES / "no_matches.html").read_text(encoding="utf-8")
    assert parse_results(page) == []


def test_parse_real_results_page():
    page = (FIXTURES / "real_results.html").read_text(encoding="utf-8")
    classes = parse_results(page)
    assert [c.class_number for c in classes] == ["30628", "30621"]
    first, second = classes
    assert first.title == "CSE 114A - 01 Found of Program Lang"
    assert first.status == "Open"
    assert (first.enrolled, first.capacity, first.seats_open) == (29, 120, 91)
    assert (second.enrolled, second.capacity, second.seats_open) == (100, 120, 20)


def test_search_form_matches_live_form_fields():
    page = (FIXTURES / "real_results.html").read_text(encoding="utf-8")
    live_fields = set(re.findall(r'name="(binds\[:[a-z_]+\]|rec_start|rec_dur)"', page))
    sent_fields = set(search_form("2270", "CSE", "101")) - {"action"}
    assert sent_fields <= live_fields


@pytest.mark.parametrize(
    ("year", "quarter", "code"),
    [(2024, "fall", "2248"), (2025, "winter", "2250"), (2025, "spring", "2252"), (2027, "Winter", "2270")],
)
def test_term_code(year, quarter, code):
    assert term_code(year, quarter) == code


def test_search_form_sets_course():
    form = search_form("2270", "CSE", "101")
    assert form["binds[:term]"] == "2270"
    assert form["binds[:subject]"] == "CSE"
    assert form["binds[:catalog_nbr]"] == "101"
    assert form["action"] == "results"


def test_rate_limiter_waits_between_calls():
    clock = [0.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        clock[0] += seconds

    limiter = RateLimiter(2.0, clock=lambda: clock[0], sleep=sleep)
    limiter.wait()
    clock[0] += 0.5
    limiter.wait()
    clock[0] += 5
    limiter.wait()
    assert slept == [1.5]


def test_client_fetch_class(results_html):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content.decode())
        return httpx.Response(200, text=results_html)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = ClassSearchClient("https://example.test/search", "test", RateLimiter(0), client=http)
    info = client.fetch_class("2270", "CSE", "101", "21240")
    assert info is not None and info.capacity == 250
    assert client.fetch_class("2270", "CSE", "101", "99999") is None
    assert len(client.fetch_course("2270", "CSE", "101")) == 2
    assert client.requests_made == 3
    assert "subject%5D=CSE" in seen[0]
    assert "catalog_nbr%5D=101" in seen[0]
