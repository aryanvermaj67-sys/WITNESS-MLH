"""Judge 2: NLI cross-encoder. Stub until Phase B4: no verdicts, so every claim is single-judge."""
from witness.models import Claim, JudgeVerdict, Passage


def judge(passages: list[Passage], claims: list[Claim]) -> dict[str, JudgeVerdict]:
    return {}
