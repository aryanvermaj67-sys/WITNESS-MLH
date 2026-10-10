"""Knowledge base: handbook Markdown → passages and sentences with stable IDs (FR-1)."""
import math
import re
from pathlib import Path

from witness.claims import sentence_spans
from witness.models import Passage, Sentence

MAX_WORDS = 150


def _sections(text: str) -> list[tuple[str, list[str]]]:
    """(heading, sentences) per section. Line 1 is the source URL; headings themselves are not sentences."""
    sections, heading, current = [], "", []
    for line in text.splitlines()[1:]:
        if re.match(r"#+\s", line):
            sections.append((heading, current))
            heading, current = line.lstrip("#").strip(), []
        else:
            current += [line[s:e] for s, e in sentence_spans(line)]
    return [(h, s) for h, s in [*sections, (heading, current)] if s]


def _chunks(sentences: list[str]) -> list[list[str]]:
    """Split one section into the fewest chunks of ≤ ~150 words, sized evenly so no tiny tail is left."""
    words = sum(len(s.split()) for s in sentences)
    n = math.ceil(words / MAX_WORDS)
    target = words / n
    chunks, current, count = [], [], 0
    for s in sentences:
        current.append(s)
        count += len(s.split())
        if count >= target and len(chunks) < n - 1:
            chunks.append(current)
            current, count = [], 0
    return [c for c in [*chunks, current] if c]


def load_kb(kb_dir: Path) -> tuple[list[Passage], dict[str, str]]:
    """Passages in file-name order, plus a title per passage id ("mlh gemma challenge: Choosing the Winner").
    Titles are for retrieval only; short sections often name their topic only in the heading."""
    passages, titles = [], {}
    for path in sorted(kb_dir.glob("*.md")):
        for heading, section in _sections(path.read_text(encoding="utf-8")):
            for chunk in _chunks(section):
                pid = f"p{len(passages) + 1}"
                sentences = [Sentence(id=f"{pid}.s{m}", text=t) for m, t in enumerate(chunk, 1)]
                passages.append(Passage(id=pid, doc=path.name, text=" ".join(chunk), sentences=sentences))
                titles[pid] = f"{path.stem.replace('_', ' ')}: {heading}"
    return passages, titles
