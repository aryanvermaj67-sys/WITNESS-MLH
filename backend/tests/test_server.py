import json

from fastapi.testclient import TestClient

from server import app
from witness.config import BACKEND

client = TestClient(app)


def test_data_routes_serve_the_backend_files():
    questions = json.loads((BACKEND / "data" / "demo_questions.json").read_text("utf-8"))
    assert client.get("/api/demo-questions").json() == questions
    backup = BACKEND / "data" / "backup_answers.json"
    expected = json.loads(backup.read_text("utf-8")) if backup.exists() else []
    assert client.get("/api/backup-answers").json() == expected
    if not (BACKEND / "eval" / "results.json").exists():  # built in Phase B6
        r = client.get("/api/eval")
        assert (r.status_code, r.json()) == (404, {"detail": "not ready"})


def test_check_validation():
    for body in [{"question": "   "}, {"question": "x" * 501}, {"question": "q", "answer_text": "x" * 4001}, {},
                 {"question": "q", "mode": "bogus"}]:
        assert client.post("/api/check", json=body).status_code == 422, body
