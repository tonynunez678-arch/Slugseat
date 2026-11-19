import sys
from pathlib import Path

import httpx

from app.config import get_settings
from app.scraper import parse_results, search_form


def main() -> None:
    if len(sys.argv) != 4:
        print("usage: python debug_fetch.py TERM SUBJECT COURSE_NUMBER   e.g. python debug_fetch.py 2270 CSE 101")
        sys.exit(1)
    term, subject, catalog = sys.argv[1], sys.argv[2].upper(), sys.argv[3].upper()
    settings = get_settings()
    with httpx.Client(headers={"User-Agent": settings.user_agent}, follow_redirects=True, timeout=20) as client:
        landing = client.get(settings.class_search_url)
        response = client.post(settings.class_search_url, data=search_form(term, subject, catalog))
    out = Path("page.html")
    out.write_text(response.text, encoding="utf-8")
    print(f"landing page status: {landing.status_code}")
    print(f"search status: {response.status_code}, final url: {response.url}, {len(response.text)} chars")
    print(f"saved to {out.resolve()}")
    classes = parse_results(response.text)
    print(f"parsed {len(classes)} classes")
    for info in classes[:10]:
        print(f"  {info}")


if __name__ == "__main__":
    main()
