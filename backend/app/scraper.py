import re
import threading
import time
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

ENROLLED_RE = re.compile(r"(\d+)\s+of\s+(\d+)\s+Enrolled", re.IGNORECASE)
CLASS_ID_RE = re.compile(r"class_id_(\d+)")
QUARTER_DIGITS = {"winter": 0, "spring": 2, "summer": 4, "fall": 8}


@dataclass(frozen=True)
class ClassInfo:
    class_number: str
    title: str
    status: str
    enrolled: int
    capacity: int

    @property
    def seats_open(self) -> int:
        return max(self.capacity - self.enrolled, 0)


def term_code(year: int, quarter: str) -> str:
    return str(2000 + (year % 100) * 10 + QUARTER_DIGITS[quarter.lower()])


def search_form(term: str, subject: str, catalog_number: str) -> dict[str, str]:
    return {
        "action": "results",
        "binds[:term]": term,
        "binds[:session_code]": "",
        "binds[:reg_status]": "all",
        "binds[:subject]": subject,
        "binds[:catalog_nbr_op]": "=",
        "binds[:catalog_nbr]": catalog_number,
        "binds[:title]": "",
        "binds[:instr_name_op]": "=",
        "binds[:instructor]": "",
        "binds[:crse_units_op]": "=",
        "binds[:crse_units_from]": "",
        "binds[:crse_units_to]": "",
        "binds[:crse_units_exact]": "",
        "binds[:days]": "",
        "binds[:times]": "",
        "binds[:acad_career]": "",
        "binds[:asynch]": "A",
        "binds[:hybrid]": "H",
        "binds[:synch]": "S",
        "binds[:person]": "P",
    }


def _clean(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def parse_results(html: str) -> list[ClassInfo]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[ClassInfo] = []
    for link in soup.find_all("a", id=CLASS_ID_RE):
        number = CLASS_ID_RE.search(link["id"]).group(1)
        panel = link.find_parent("div", class_="panel") or link.parent
        heading = link.find_parent(["h2", "h3"]) or panel
        status_tag = heading.find(class_="sr-only")
        status = _clean(status_tag.get_text()) if status_tag else ""
        match = ENROLLED_RE.search(_clean(panel.get_text(" ")))
        if not match:
            continue
        results.append(
            ClassInfo(
                class_number=number,
                title=_clean(link.get_text()),
                status=status,
                enrolled=int(match.group(1)),
                capacity=int(match.group(2)),
            )
        )
    return results


class RateLimiter:
    def __init__(self, min_interval: float, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last is not None:
                remaining = self.min_interval - (now - self._last)
                if remaining > 0:
                    self._sleep(remaining)
                    now = self._clock()
            self._last = now


class ClassSearchClient:
    def __init__(self, url: str, user_agent: str, limiter: RateLimiter, timeout: float = 15.0, client: httpx.Client | None = None):
        self.url = url
        self.limiter = limiter
        self.requests_made = 0
        self._client = client or httpx.Client(timeout=timeout, headers={"User-Agent": user_agent}, follow_redirects=True)

    def fetch_course(self, term: str, subject: str, catalog_number: str) -> list[ClassInfo]:
        self.limiter.wait()
        self.requests_made += 1
        response = self._client.post(self.url, data=search_form(term, subject, catalog_number))
        response.raise_for_status()
        return parse_results(response.text)

    def fetch_class(self, term: str, subject: str, catalog_number: str, class_number: str) -> ClassInfo | None:
        for info in self.fetch_course(term, subject, catalog_number):
            if info.class_number == class_number:
                return info
        return None

    def close(self) -> None:
        self._client.close()
