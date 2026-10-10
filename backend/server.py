"""WITNESS FastAPI server (REQUIREMENTS.md §5). Phase B1: every route returns its contracts/examples file."""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from witness import judge_nli, pipeline
from witness.config import settings
from witness.kb import load_kb
from witness.models import (BackupAnswer, CheckRequest, DemoQuestion, EvalResult, Health, PipelineResult,
                            ReplayEntry)
from witness.retrieval import Retriever, load_embedder

EXAMPLES = Path(__file__).resolve().parent.parent / "contracts" / "examples"


def example(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@asynccontextmanager
async def lifespan(app):
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


@app.get("/api/health", response_model=Health)
def health():
    return example("health.json")


@app.get("/api/demo-questions", response_model=list[DemoQuestion])
def demo_questions():
    return example("demo_questions.json")


@app.post("/api/check", response_model=PipelineResult)
def check(req: CheckRequest):
    if req.mode == "replay":  # replay is still the example file until Phase B5
        return example("check_replay.json")
    # a missing retriever (index failed to load) becomes an error in the result, not an HTTP 500
    return pipeline.run_pipeline(req.question, req.answer_text, getattr(app.state, "retriever", None),
                                 getattr(app.state, "nli", None))


@app.get("/api/eval", response_model=EvalResult)
def eval_result():
    return example("eval.json")


@app.get("/api/backup-answers", response_model=list[BackupAnswer])
def backup_answers():
    return example("backup_answers.json")


@app.get("/api/replay", response_model=list[ReplayEntry])
def replay_index():
    return example("replay_index.json")


@app.get("/api/replay/{key}", response_model=PipelineResult)
def replay(key: str):
    if key not in {e["key"] for e in example("replay_index.json")}:
        raise HTTPException(404, "not found")
    return example("check_replay.json")
