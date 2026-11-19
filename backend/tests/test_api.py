from app.models import ClassSnapshot


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_terms_starts_at_current_quarter(client):
    terms = client.get("/api/terms", params={"today": "2026-11-19"}).json()
    assert [t["code"] for t in terms] == ["2268", "2270", "2272", "2274"]
    assert terms[1]["name"] == "2027 Winter"


def test_create_and_list_watch(client, session_factory):
    with session_factory() as session:
        session.add(ClassSnapshot(term="2270", class_number="21234", title="CSE 101", status="Open", enrolled=38, capacity=40))
        session.commit()

    response = client.post("/api/watches", json={"email": "Slug@UCSC.edu", "term": "2270", "class_number": "21234"})
    assert response.status_code == 201
    body = response.json()
    assert body["class_status"]["seats_open"] == 2

    watches = client.get("/api/watches", params={"email": "slug@ucsc.edu"}).json()
    assert [w["class_number"] for w in watches] == ["21234"]


def test_duplicate_watch_is_reused(client):
    payload = {"email": "a@ucsc.edu", "term": "2270", "class_number": "21234"}
    first = client.post("/api/watches", json=payload).json()
    second = client.post("/api/watches", json=payload).json()
    assert first["id"] == second["id"]


def test_rejects_bad_input(client):
    assert client.post("/api/watches", json={"email": "nope", "term": "2270", "class_number": "21234"}).status_code == 422
    assert client.post("/api/watches", json={"email": "a@ucsc.edu", "term": "2270", "class_number": "12"}).status_code == 422
    bad_phone = {"email": "a@ucsc.edu", "term": "2270", "class_number": "21234", "phone": "555"}
    assert client.post("/api/watches", json=bad_phone).status_code == 422


def test_delete_requires_matching_email(client):
    watch = client.post("/api/watches", json={"email": "a@ucsc.edu", "term": "2270", "class_number": "21234"}).json()
    assert client.delete(f"/api/watches/{watch['id']}", params={"email": "b@ucsc.edu"}).status_code == 404
    assert client.delete(f"/api/watches/{watch['id']}", params={"email": "a@ucsc.edu"}).status_code == 204
    assert client.get("/api/watches", params={"email": "a@ucsc.edu"}).json() == []


def test_metrics(client):
    client.post("/api/watches", json={"email": "a@ucsc.edu", "term": "2270", "class_number": "21234"})
    metrics = client.get("/api/metrics").json()
    assert metrics["users"] == 1
    assert metrics["active_watches"] == 1
    assert metrics["median_alert_latency_seconds"] is None
