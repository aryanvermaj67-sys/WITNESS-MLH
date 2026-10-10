"""Uploaded PDFs: extract the text, build passages like the handbook's, and keep a private search index in memory.

Nothing from an upload is written to disk and nothing is cached for replay. Limits keep a single upload cheap.
Scanned (image-only) PDFs have no text to read; OCR is out of scope.
"""
import hashlib
import io
import re
import threading
from collections import OrderedDict
from contextlib import nullcontext
from dataclasses import dataclass

from pypdf import PdfReader

from witness.claims import sentence_spans
from witness.kb import _chunks
from witness.models import Passage, Sentence
from witness.retrieval import Retriever

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 100
MAX_CHARS = 300_000
MIN_WORDS = 20
MAX_DOCS = 5  # the oldest upload is dropped when a sixth arrives

_TERMINAL = (".", "!", "?", ":", ";")
_BULLET = re.compile(r"(?:[-*•–]\s|\d+[.)]\s)")


class DocumentError(ValueError):
    """The message is meant to be shown to the person who uploaded the file."""


@dataclass
class Document:
    id: str
    name: str
    pages: int
    words: int
    retriever: Retriever

    @property
    def passages(self) -> list[Passage]:
        return self.retriever.passages


def clean_name(name: str) -> str:
    name = re.sub(r"[\x00-\x1f\x7f]", "", name.replace("\\", "/").rsplit("/", 1)[-1]).strip()
    return (name or "document.pdf")[:100]


def read_pages(data: bytes) -> list[str]:
    """Raw text of every page. Raises DocumentError with a friendly message for anything unusable."""
    if len(data) > MAX_BYTES:
        raise DocumentError("That PDF is larger than 10 MB. Please upload a smaller file.")
    if not data.lstrip()[:5].startswith(b"%PDF"):
        raise DocumentError("That file is not a PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentError("This PDF is password-protected. Remove the password and upload it again.")
        if len(reader.pages) > MAX_PAGES:
            raise DocumentError(f"That PDF has more than {MAX_PAGES} pages. Please upload a shorter one.")
        return [page.extract_text() or "" for page in reader.pages]
    except DocumentError:
        raise
    except Exception:
        raise DocumentError("That PDF could not be read. The file may be damaged.") from None


def _unwrap(text: str) -> list[str]:
    """Paragraphs of one page. PDFs break lines mid-sentence, so wrapped lines are joined; a line that ends a sentence,
    a short heading-like line, and a bullet each keep their own break."""
    # PDF bullets and odd glyphs often come out as control characters or U+FFFD: never pass those on to a model
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f�]", " ", text)
    text = text.replace("\r", "\n").replace("­", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # "exam-\nple" -> "example"
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        current = ""
        for raw in block.split("\n"):
            line = re.sub(r"\s+", " ", raw).strip()
            if not line:
                continue
            if current:
                heading_like = len(current) < 50 and (line[0].isupper() or line[0].isdigit())
                if current.endswith(_TERMINAL) or heading_like or _BULLET.match(line):
                    paragraphs.append(current)
                    current = line
                else:
                    current = f"{current} {line}"
            else:
                current = line
        if current:
            paragraphs.append(current)
    return paragraphs


def build_passages(name: str, pages: list[str]) -> tuple[list[Passage], dict[str, str]]:
    """Passages (60-150 words, never across pages) with stable ids p{n} / p{n}.s{m}, like kb.load_kb."""
    passages, titles = [], {}
    stem = re.sub(r"\.pdf$", "", name, flags=re.I)
    for number, text in enumerate(pages, 1):
        sentences = [para[s:e] for para in _unwrap(text) for s, e in sentence_spans(para)]
        for chunk in _chunks(sentences) if sentences else []:
            pid = f"p{len(passages) + 1}"
            passages.append(Passage(id=pid, doc=name, text=" ".join(chunk),
                                    sentences=[Sentence(id=f"{pid}.s{m}", text=t) for m, t in enumerate(chunk, 1)]))
            titles[pid] = f"{stem}: page {number}"
    return passages, titles


class DocumentStore:
    """Uploaded documents, in memory only. add() is slow (it embeds the text), so the caller passes the lock that
    serialises use of the embedding model with live checks."""

    def __init__(self, embedder):
        self._embedder = embedder
        self._docs: OrderedDict[str, Document] = OrderedDict()
        self._mutex = threading.Lock()

    def add(self, name: str, data: bytes, model_lock=None) -> Document:
        name = clean_name(name)
        doc_id = hashlib.sha1(data).hexdigest()[:12]
        with self._mutex:
            if doc_id in self._docs:  # the same file again: reuse it
                self._docs.move_to_end(doc_id)
                return self._docs[doc_id]
        pages = read_pages(data)
        if sum(len(p) for p in pages) > MAX_CHARS:
            raise DocumentError("That PDF contains too much text for one upload. Please upload a shorter one.")
        passages, titles = build_passages(name, pages)
        words = sum(len(p.text.split()) for p in passages)
        if words < MIN_WORDS:
            raise DocumentError("No readable text was found in that PDF. Scanned (image-only) PDFs are not supported yet.")
        with model_lock or nullcontext():
            retriever = Retriever(passages, titles, self._embedder)
        doc = Document(id=doc_id, name=name, pages=len(pages), words=words, retriever=retriever)
        with self._mutex:
            self._docs[doc_id] = doc
            while len(self._docs) > MAX_DOCS:
                self._docs.popitem(last=False)
        return doc

    def get(self, doc_id: str) -> Document | None:
        with self._mutex:
            return self._docs.get(doc_id)

    def list(self) -> list[Document]:
        with self._mutex:
            return list(self._docs.values())

    def remove(self, doc_id: str) -> bool:
        with self._mutex:
            return self._docs.pop(doc_id, None) is not None
