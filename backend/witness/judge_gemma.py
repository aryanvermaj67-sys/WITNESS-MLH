"""Judge 1: Gemma through the Gemini API, ONE call for all claims (FR-6, prompt §9.2).

The model id comes from GEMINI_MODEL. At the time of writing gemma-4-31b-it answers in 25-50 s and often returns
500/503 ("high demand"), while gemma-4-26b-a4b-it answers in about 7 s; hence the retries and the generous budget.
"""
import json
import sys
import time

from google import genai
from google.genai import types

from witness.config import settings
from witness.models import Claim, JudgeVerdict, Passage

SYSTEM = ("You are a strict fact-checker. For each claim, decide using ONLY the numbered sentences. supported = a sentence "
          "states it. contradicted = a sentence states the opposite or a different value. unsupported = no sentence says "
          "it either way. Cite sentence IDs. Return JSON only.")
OUTPUT_SPEC = ('Return a JSON array: [{"claim_id": "c1", "label": "supported|unsupported|contradicted", '
               '"evidence_ids": ["p1.s3"], "explanation": "One short sentence."}]')
LABELS = ("supported", "unsupported", "contradicted")
BUDGET = 50.0           # seconds for the whole judge step, retries included (pipeline soft limit is 60 s)
ATTEMPT_TIMEOUT = 40.0  # seconds per attempt, capped by what is left of the budget
MAX_ATTEMPTS = 4
RETRY_CODES = {429, 500, 502, 503, 504}


def build_content(passages: list[Passage], claims: list[Claim]) -> str:
    sentences = "\n".join(f"{s.id}: {s.text}" for p in passages for s in p.sentences)
    claim_lines = "\n".join(f"{c.id}: {c.text}" for c in claims)
    return f"Sentences:\n{sentences}\n\nClaims:\n{claim_lines}\n\n{OUTPUT_SPEC}"


def parse(raw: str, claims: list[Claim], passages: list[Passage]) -> tuple[dict[str, JudgeVerdict], str | None]:
    """Strict validation of the model's reply. Returns ({claim_id: verdict}, error)."""
    start, end = (raw or "").find("["), (raw or "").rfind("]")
    try:
        items = json.loads(raw[start:end + 1]) if 0 <= start < end else None
    except ValueError:
        items = None
    if not isinstance(items, list):
        return {}, "Gemma judge returned output that could not be read, so these claims have no Gemma verdict."
    claim_ids = {c.id for c in claims}
    sentence_ids = {s.id for p in passages for s in p.sentences}
    verdicts: dict[str, JudgeVerdict] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("claim_id") not in claim_ids or item["claim_id"] in verdicts:
            continue  # unknown claim id (or a repeat): ignored
        if item.get("label") not in LABELS:
            continue  # invalid label: that claim simply has no verdict
        ids = item.get("evidence_ids")
        evidence = list(dict.fromkeys(i for i in (ids if isinstance(ids, list) else []) if i in sentence_ids))  # unknown ids dropped
        explanation = item.get("explanation")
        verdicts[item["claim_id"]] = JudgeVerdict(
            claim_id=item["claim_id"], judge="gemma", label=item["label"], evidence_ids=evidence,
            explanation=explanation.strip() if isinstance(explanation, str) else "", confidence=None)
    return verdicts, None


def _call(client, content: str, timeout: float, thinking: bool) -> str:
    config = types.GenerateContentConfig(
        temperature=0, system_instruction=SYSTEM, response_mime_type="application/json",
        http_options=types.HttpOptions(timeout=int(timeout * 1000)),
        # MINIMAL keeps the model from spending its time on hidden reasoning; the budget setting is not supported
        thinking_config=types.ThinkingConfig(thinking_level="MINIMAL") if thinking else None)
    return client.models.generate_content(model=settings.GEMINI_MODEL, contents=content, config=config).text or ""


def judge(passages: list[Passage], claims: list[Claim], client=None, sleep=time.sleep,
          clock=time.monotonic) -> tuple[dict[str, JudgeVerdict], list[str]]:
    """({claim_id: verdict}, errors). One Gemini call (plus retries on 429/5xx); never raises."""
    if not claims:
        return {}, []
    key = settings.GEMINI_API_KEY.get_secret_value()
    if client is None and not key:
        return {}, ["Gemini API key is missing (GEMINI_API_KEY in backend/.env), so there is no Gemma verdict."]
    try:
        client = client or genai.Client(api_key=key)
        content = build_content(passages, claims)
    except Exception:
        return {}, ["Gemma judge could not start, so these claims have no Gemma verdict."]
    deadline, thinking, last = clock() + BUDGET, True, ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        left = deadline - clock()
        if left < 5:
            break
        try:
            return _finish(_call(client, content, min(ATTEMPT_TIMEOUT, left), thinking), claims, passages)
        except Exception as e:
            code = getattr(e, "code", None)
            last = f"HTTP {code}" if code else type(e).__name__
            # for the server log only (never shown in the app); the key is masked
            message = str(e).replace(key, "***") if key else str(e)
            print(f"Gemma judge attempt {attempt}/{MAX_ATTEMPTS} failed: {message[:300]}", file=sys.stderr, flush=True)
            if code == 400 and thinking:
                thinking = False  # this model/SDK rejects the thinking setting: retry without it
            elif code not in RETRY_CODES and code is not None:
                break
            sleep(1)
    return {}, [f"Gemma judge ({settings.GEMINI_MODEL}) did not answer ({last or 'out of time'}), so these claims have no Gemma verdict."]


def _finish(raw, claims, passages):
    verdicts, error = parse(raw, claims, passages)
    return verdicts, [error] if error else []
