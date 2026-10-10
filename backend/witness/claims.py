"""Sentence splitting with exact character offsets (FR-5). kb.py uses the same splitter for the handbook."""
import re

from witness.models import Claim

# sentence end = . ! ? then whitespace (not after "e.g." / "i.e." / "Ex."), or a line break
_BOUNDARY = re.compile(r"(?<!e\.g\.)(?<!i\.e\.)(?<!Ex\.)(?<=[.!?])\s+|\s*\n\s*")
# list markers like "- ", "* ", "1. ", "1.Text", "2) " at the start of a sentence are not part of it
_MARKER = re.compile(r"(?:[-*•]\s+|\d+[.)](?!\d)\s*)")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence in text, whitespace and list markers excluded."""
    spans, start = [], 0
    for m in [*_BOUNDARY.finditer(text), None]:
        end = m.start() if m else len(text)
        while start < end and text[start].isspace():
            start += 1
        marker = _MARKER.match(text, start, end)
        if marker:
            start = marker.end()
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            spans.append((start, end))
        start = m.end() if m else end
    return spans


def split_claims(answer_text: str) -> list[Claim]:
    """One claim per sentence; fragments under 4 words are dropped."""
    spans = [(s, e) for s, e in sentence_spans(answer_text) if len(answer_text[s:e].split()) >= 4]
    return [Claim(id=f"c{i}", text=answer_text[s:e], start=s, end=e) for i, (s, e) in enumerate(spans, 1)]
