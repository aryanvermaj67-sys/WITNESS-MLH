"""Combine rule (REQUIREMENTS.md §7) and trust score (FR-8, FR-9)."""
from witness.models import FinalVerdict, JudgeVerdict, TrustScore

# (gemma label, nli label) -> final label, when both judges answered
COMBINE = {
    ("supported", "supported"): "supported",
    ("supported", "unsupported"): "supported",
    ("supported", "contradicted"): "needs_review",
    ("unsupported", "supported"): "needs_review",
    ("unsupported", "unsupported"): "unsupported",
    ("unsupported", "contradicted"): "needs_review",
    ("contradicted", "contradicted"): "contradicted",
    ("contradicted", "unsupported"): "contradicted",
    ("contradicted", "supported"): "needs_review",
}


def combine(claim_id: str, gemma: JudgeVerdict | None, nli: JudgeVerdict | None) -> FinalVerdict:
    if gemma and nli:
        label, single = COMBINE[(gemma.label, nli.label)], False
    elif gemma or nli:
        label, single = (gemma or nli).label, True  # one judge answered: use it and flag it
    else:
        label, single = "needs_review", True
    evidence = list(dict.fromkeys([*(gemma.evidence_ids if gemma else []), *(nli.evidence_ids if nli else [])]))
    explanation = (gemma.explanation if gemma else "") or (nli.explanation if nli else "")
    return FinalVerdict(claim_id=claim_id, label=label, evidence_ids=evidence,
                        explanation=explanation or "No judge returned a verdict for this claim.",
                        gemma=gemma, nli=nli, single_judge=single)


def trust(verdicts: list[FinalVerdict]) -> TrustScore:
    counts = {label: sum(v.label == label for v in verdicts) for label in ("supported", "unsupported", "contradicted", "needs_review")}
    total = len(verdicts)
    return TrustScore(**counts, total=total, percent_supported=round(100 * counts["supported"] / total) if total else 0)
