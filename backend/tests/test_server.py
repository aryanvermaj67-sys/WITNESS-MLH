from fastapi.testclient import TestClient

from server import app, example

client = TestClient(app)


def test_get_routes_return_examples():
    key = client.get("/api/replay").json()[0]["key"]
    routes = {"/api/health": "health.json", "/api/demo-questions": "demo_questions.json", "/api/eval": "eval.json",
              "/api/backup-answers": "backup_answers.json", "/api/replay": "replay_index.json",
              f"/api/replay/{key}": "check_replay.json"}
    for path, name in routes.items():
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.json() == example(name), path
    assert client.get("/api/replay/missing").status_code == 404


def test_check_validation():
    for body in [{"question": "   "}, {"question": "x" * 501}, {"question": "q", "answer_text": "x" * 4001}, {},
                 {"question": "q", "mode": "bogus"}]:
        assert client.post("/api/check", json=body).status_code == 422, body
