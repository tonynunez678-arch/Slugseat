# SlugSeat

Get a text or email the moment a seat opens in a UCSC class.

Students add the term, subject, course number, and the 5-digit class number of their section. A background poller checks the public UCSC class search, and when a full class gets an open seat, everyone watching it is notified once.

## Stack

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL
- **Poller:** rate-limited scraper with a shared per-class cache
- **Alerts:** email over SMTP, texts through Twilio, or console output for development
- **Frontend:** React and Vite
- **CI:** pytest and a frontend build on GitHub Actions

## How it works

1. `POST /api/watches` saves a user and the class they want.
2. `python -m app.poller` groups watches by course (for example CSE 101) and runs one class search per course, which returns every section at once. Each course is fetched at most once per cache window, no matter how many people or sections are watched, and requests are spaced out by a rate limiter.
3. When a class goes from full to having open seats, each watcher gets one alert. If the class fills up again and later reopens, they are alerted again.
4. Every alert is stored with the time the seat was detected and the time it was sent, so `GET /api/metrics` can report users, watches, alerts sent, and median alert latency.

## Run locally

Start Postgres:

```bash
docker compose up -d db
```

Backend API:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env
uvicorn app.main:app --reload
```

Poller, in a second terminal:

```bash
cd backend && source .venv/bin/activate
python -m app.poller
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Without Postgres, the backend falls back to a local SQLite file.

## Checking the live class search

```bash
cd backend
python debug_fetch.py 2270 CSE 101
```

This saves the results page to `page.html` and prints the sections the scraper found.

## Tests

```bash
cd backend && pytest
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/terms` | Current and upcoming term codes |
| POST | `/api/watches` | Watch a section: `email`, `term`, `subject`, `catalog_number`, `class_number`, optional `phone` in `+1...` format |
| GET | `/api/watches?email=` | List a user's active watches with the latest seat counts |
| DELETE | `/api/watches/{id}?email=` | Stop watching |
| GET | `/api/metrics` | Usage and alert latency numbers |

## Term codes

UCSC term codes are `2` + two-digit year + quarter digit: winter `0`, spring `2`, summer `4`, fall `8`. Fall 2026 is `2268`, Winter 2027 is `2270`.

## Responsible use

- Only alerts people who opted in.
- One request per class per cache window, at least 2 seconds apart by default.
- Identifies itself with a clear User-Agent.
- Check UCSC's acceptable-use policy before deploying.

## Roadmap

- Verify email addresses before sending alerts
- Look up sections automatically so students only need to enter the course
- Deploy the API and poller on Render or Fly.io
- Alerting when the class search layout changes and parsing fails
