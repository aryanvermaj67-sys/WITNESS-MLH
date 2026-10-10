"""WITNESS FastAPI server (REQUIREMENTS.md §5). Phase B1: every route returns its contracts/examples file."""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from witness.models import (BackupAnswer, CheckRequest, DemoQuestion, EvalResult, Health, PipelineResult,
                            ReplayEntry)

EXAMPLES = Path(__file__).resolve().parent.parent / "contracts" / "examples"


def example(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@asynccontextmanager
async def lifespan(app):
    # models, KB and indexes load here once (NFR-4), from Phase B2 on
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
    return example("check_pasted.json" if req.answer_text else "check_mixed.json")


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
