import httpx
import pytest

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


@pytest.mark.parametrize(
    ("year", "quarter", "code"),
    [(2024, "fall", "2248"), (2025, "winter", "2250"), (2025, "spring", "2252"), (2027, "Winter", "2270")],
)
def test_term_code(year, quarter, code):
    assert term_code(year, quarter) == code


def test_search_form_sets_class_number():
    form = search_form("2270", class_number="21234")
    assert form["binds[:term]"] == "2270"
    assert form["binds[:class_nbr]"] == "21234"
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
    info = client.fetch_class("2270", "21240")
    assert info is not None and info.capacity == 250
    assert client.fetch_class("2270", "99999") is None
    assert client.requests_made == 2
    assert "class_nbr%5D=21240" in seen[0]
