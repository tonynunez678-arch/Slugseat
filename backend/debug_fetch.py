import sys
from pathlib import Path

import httpx

from app.config import get_settings
from app.scraper import parse_results, search_form


def main() -> None:
    term = sys.argv[1] if len(sys.argv) > 1 else "2270"
    class_number = sys.argv[2] if len(sys.argv) > 2 else ""
    settings = get_settings()
    with httpx.Client(headers={"User-Agent": settings.user_agent}, follow_redirects=True, timeout=20) as client:
        landing = client.get(settings.class_search_url)
        response = client.post(settings.class_search_url, data=search_form(term, class_number=class_number))
    out = Path("page.html")
    out.write_text(response.text, encoding="utf-8")
    print(f"landing page status: {landing.status_code}")
    print(f"search status: {response.status_code}, final url: {response.url}, {len(response.text)} chars")
    print(f"saved to {out.resolve()}")
    classes = parse_results(response.text)
    print(f"parsed {len(classes)} classes")
    for info in classes[:5]:
        print(f"  {info}")


if __name__ == "__main__":
    main()
