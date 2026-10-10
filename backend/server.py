"""WITNESS FastAPI server (REQUIREMENTS.md §5)."""
import json
import threading
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from witness import cache, judge_nli, pipeline
from witness.config import BACKEND, settings
from witness.kb import load_kb
from witness.models import (BackupAnswer, CheckRequest, DemoQuestion, EvalResult, Health, PipelineResult,
                            ReplayEntry)
from witness.retrieval import Retriever, load_embedder

VERSION = "0.1.0"


def _watch_lmstudio(state):
    # pinging "localhost" takes ~1.7 s on Windows even when LM Studio is up (IPv6 first), so /api/health
    # reads the last result of this background ping instead of waiting for one (§5: health < 300 ms)
    while True:
        try:
            state.lmstudio = httpx.get(f"{settings.LMSTUDIO_BASE_URL}/models", timeout=1.0).status_code == 200
        except Exception:
            state.lmstudio = False
        time.sleep(5)


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=_watch_lmstudio, args=(app.state,), daemon=True).start()
    # KB, embedding model and search indexes load here once (NFR-4)
    passages, titles = load_kb(settings.path(settings.KB_DIR))
    app.state.retriever = Retriever(passages, titles, load_embedder(settings.EMBED_MODEL))
    try:
        app.state.nli = judge_nli.load_model(settings.NLI_MODEL, settings.NLI_DEVICE)
    except Exception as e:  # server still starts; every check then reports the missing NLI judge in `errors`
        print(f"NLI model not loaded ({type(e).__name__}); checks will run with the Gemma judge only.")
    yield


app = FastAPI(title="WITNESS", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"],
                   allow_headers=["Content-Type"])


def _read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


@app.get("/api/health", response_model=Health)
def health():
    retriever = getattr(app.state, "retriever", None)
    return Health(status="ok", version=VERSION, lmstudio=getattr(app.state, "lmstudio", False),
                  gemini_key=bool(settings.GEMINI_API_KEY.get_secret_value()),
                  nli_loaded=getattr(app.state, "nli", None) is not None, embeddings_loaded=retriever is not None,
                  kb_passages=len(retriever.passages) if retriever else 0, replay_default=settings.OFFLINE_REPLAY,
                  models={"writer": f"{settings.LMSTUDIO_MODEL} (LM Studio, local)",
                          "judge_1": f"{settings.GEMINI_MODEL} (Gemini API)",
                          "judge_2": f"{settings.NLI_MODEL} (local, {settings.NLI_DEVICE.upper()})"})


@app.get("/api/demo-questions", response_model=list[DemoQuestion])
def demo_questions():
    return _read_json(BACKEND / "data" / "demo_questions.json", [])


@app.post("/api/check", response_model=PipelineResult)
def check(req: CheckRequest):
    if (req.mode or ("replay" if settings.OFFLINE_REPLAY else "live")) == "replay":
        key = cache.key_for(req.question, req.answer_text)
        return cache.load_result(key) or cache.missing(req.question, req.answer_text)
    # a missing retriever (index failed to load) becomes an error in the result, not an HTTP 500
    return pipeline.run_pipeline(req.question, req.answer_text, getattr(app.state, "retriever", None),
                                 getattr(app.state, "nli", None))


@app.get("/api/eval", response_model=EvalResult)
def eval_result():
    path = BACKEND / "eval" / "results.json"
    if not path.exists():
        raise HTTPException(404, "not ready")
    return _read_json(path, None)


@app.get("/api/backup-answers", response_model=list[BackupAnswer])
def backup_answers():
    return _read_json(BACKEND / "data" / "backup_answers.json", [])


@app.get("/api/replay", response_model=list[ReplayEntry])
def replay_index():
    return cache.load_index()


@app.get("/api/replay/{key}", response_model=PipelineResult)
def replay(key: str):
    result = cache.load_result(key)
    if result is None:
        raise HTTPException(404, "not found")
    return result


# Registered last, so every /api route above wins (FR-14). Serves FRONTEND_DIST when it exists, with SPA fallback.
@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    dist = settings.path(settings.FRONTEND_DIST)
    if path == "api" or path.startswith("api/") or not (dist / "index.html").is_file():
        raise HTTPException(404, "Not Found")
    file = (dist / path).resolve()
    if path and file.is_file() and file.is_relative_to(dist):  # no path traversal out of dist
        return FileResponse(file)
    return FileResponse(dist / "index.html")
