"""Judge 2: NLI cross-encoder on CPU (FR-7).

Decision rule (supersedes REQUIREMENTS.md §7 for NLI, see PROGRESS.md -> Decisions):
DeBERTa calls most UNRELATED sentence pairs "contradiction", so a contradiction only counts from sentences related
to the claim, and entailment is checked first. Per claim only its NLI_RELATED_K most similar sentences are scored.
"""
from collections.abc import Callable

import numpy as np
from sentence_transformers import CrossEncoder

from witness.config import settings
from witness.models import Claim, JudgeVerdict, Passage

# related(claim_text, sentence_ids, k) -> [(sentence_id, cosine similarity)], best first (Retriever.related)
Related = Callable[[str, list[str], int], list[tuple[str, float]]]


def load_model(name: str, device: str) -> CrossEncoder:
    # local_files_only: loads from the HF cache, never the network
    return CrossEncoder(name, device=device, local_files_only=True)


def _decide(claim_id, candidates, probs, contra_i, entail_i) -> JudgeVerdict:
    """candidates: [(sentence_id, similarity)]; probs: one softmax row per candidate."""
    je = int(probs[:, entail_i].argmax())
    me = float(probs[je, entail_i])
    related = [j for j, (_, sim) in enumerate(candidates) if sim >= settings.NLI_RELATED_MIN_SIM]
    jc = max(related, key=lambda j: probs[j, contra_i], default=None)
    mc = float(probs[jc, contra_i]) if jc is not None else 0.0
    if me >= settings.NLI_ENTAIL_THRESHOLD:
        label, evidence, conf, why = "supported", [candidates[je][0]], me, f"entailment {me:.2f}"
    elif mc >= settings.NLI_CONTRA_THRESHOLD:
        label, evidence, conf, why = "contradicted", [candidates[jc][0]], mc, f"contradiction {mc:.2f}"
    else:
        label, evidence, conf = "unsupported", [], max(me, mc)
        why = f"no sentence above threshold (entail {me:.2f}, contra {mc:.2f})"
    return JudgeVerdict(claim_id=claim_id, judge="nli", label=label, evidence_ids=evidence, explanation=why,
                        confidence=round(conf, 2))


def judge(passages: list[Passage], claims: list[Claim], model, related: Related | None) -> dict[str, JudgeVerdict]:
    """Score (premise=sentence, hypothesis=claim) for each claim's related sentences, all in one batch.
    Never raises: any failure (including a missing model) returns {} and the pipeline reports it."""
    try:
        text = {s.id: s.text for p in passages for s in p.sentences}
        if not claims or not text or model is None or related is None:
            return {}
        index = {label.lower(): int(i) for i, label in model.config.id2label.items()}
        candidates = [related(c.text, list(text), settings.NLI_RELATED_K) for c in claims]
        pairs = [(text[sid], c.text) for c, cands in zip(claims, candidates) for sid, _ in cands]
        logits = np.asarray(model.predict(pairs, convert_to_numpy=True), dtype=float)  # raw logits
        probs = np.exp(logits - logits.max(-1, keepdims=True))
        probs /= probs.sum(-1, keepdims=True)
        out, row = {}, 0
        for c, cands in zip(claims, candidates):
            out[c.id] = _decide(c.id, cands, probs[row:row + len(cands)], index["contradiction"], index["entailment"])
            row += len(cands)
        return out
    except Exception:
        return {}
