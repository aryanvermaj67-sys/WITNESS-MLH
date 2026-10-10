"""Pydantic v2 models for REQUIREMENTS.md §4. Field names must match contracts/examples exactly."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

JudgeLabel = Literal["supported", "unsupported", "contradicted"]
FinalLabel = Literal["supported", "unsupported", "contradicted", "needs_review"]
JudgeName = Literal["gemma", "nli"]
AnswerSource = Literal["gemma-4-e2b-local", "pasted"]
Mode = Literal["live", "replay"]


class Model(BaseModel):
    # unknown fields fail validation, so a contract drift is caught by the tests
    model_config = ConfigDict(extra="forbid")


class Sentence(Model):
    id: str
    text: str


class Passage(Model):
    id: str
    doc: str
    text: str
    sentences: list[Sentence]


class Claim(Model):
    id: str
    text: str
    start: int
    end: int


class JudgeVerdict(Model):
    claim_id: str
    judge: JudgeName
    label: JudgeLabel
    evidence_ids: list[str]
    explanation: str
    confidence: float | None


class FinalVerdict(Model):
    claim_id: str
    label: FinalLabel
    evidence_ids: list[str]
    explanation: str
    gemma: JudgeVerdict | None
    nli: JudgeVerdict | None
    single_judge: bool


class TrustScore(Model):
    supported: int
    unsupported: int
    contradicted: int
    needs_review: int
    total: int
    percent_supported: int


class PipelineResult(Model):
    question: str
    answer_text: str
    answer_source: AnswerSource
    passages: list[Passage]
    claims: list[Claim]
    verdicts: list[FinalVerdict]
    trust: TrustScore
    fixed_answer: str
    timings: dict[str, float]
    errors: list[str]
    mode: Mode


class HealthModels(Model):
    writer: str
    judge_1: str
    judge_2: str


class Health(Model):
    status: str
    version: str
    lmstudio: bool
    gemini_key: bool
    nli_loaded: bool
    embeddings_loaded: bool
    kb_passages: int
    replay_default: bool
    models: HealthModels


class DemoQuestion(Model):
    id: str
    question: str
    expect: FinalLabel
    why: str


class EvalRow(Model):
    judge: Literal["gemma", "nli", "combined"]
    label: str
    accuracy: float
    correct: int
    n: int


class LabelCount(Model):
    n: int


class EvalResult(Model):
    is_example: bool
    note: str
    n_claims: int
    generated_at: str
    rows: list[EvalRow]
    per_label: dict[str, LabelCount]


class BackupAnswer(Model):
    id: str
    question: str
    answer: str
    source: str
    is_example: bool


class CheckRequest(BaseModel):
    """POST /api/check body (§5). Invalid input → FastAPI's standard 422."""
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    answer_text: Annotated[str, StringConstraints(max_length=4000)] | None = None
    mode: Mode | None = None


class ReplayEntry(Model):
    key: str
    question: str
    answer_source: AnswerSource
    saved_at: str
