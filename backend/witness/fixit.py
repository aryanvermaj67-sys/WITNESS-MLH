"""Fix-it (FR-10): only supported claims, each followed by its first evidence id. Deterministic, no API call."""
from witness.models import Claim, FinalVerdict


def fixed_answer(claims: list[Claim], verdicts: list[FinalVerdict]) -> str:
    by_id = {v.claim_id: v for v in verdicts}
    parts = []
    for c in claims:
        v = by_id.get(c.id)
        if v and v.label == "supported":
            parts.append(f"{c.text} [{v.evidence_ids[0]}]" if v.evidence_ids else c.text)
    return " ".join(parts)
