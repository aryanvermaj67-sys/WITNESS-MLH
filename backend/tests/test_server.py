from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def test_get_routes():
    key = client.get("/api/replay").json()[0]["key"]
    for path in ["/api/health", "/api/demo-questions", "/api/eval", "/api/backup-answers", f"/api/replay/{key}"]:
        assert client.get(path).status_code == 200, path
    assert client.get("/api/replay/missing").status_code == 404


def test_check():
    assert client.post("/api/check", json={"question": "q"}).json()["answer_source"] == "gemma-4-e2b-local"
    assert client.post("/api/check", json={"question": "q", "answer_text": "a"}).json()["answer_source"] == "pasted"


def test_check_validation():
    for body in [{"question": "   "}, {"question": "x" * 501}, {"question": "q", "answer_text": "x" * 4001}, {}]:
        assert client.post("/api/check", json=body).status_code == 422, body
