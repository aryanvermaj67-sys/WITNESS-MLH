"""Hybrid retrieval: BM25 + MiniLM embeddings merged by reciprocal rank fusion (FR-2)."""
import re

from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from witness.models import Passage


def load_embedder(name: str) -> SentenceTransformer:
    # CPU keeps the GPU for LM Studio; local_files_only works offline from the HF cache
    return SentenceTransformer(name, device="cpu", local_files_only=True)


_STOP = set("a an the and or but if of to in on at by for with from as is are was were be been do does did can could "
             "should would will we you they it our your their what which who how when where why this that these those "
             "there".split())


def _stem(word: str) -> str:
    """Light suffix stripping so "win"/"winning" and "team"/"teams" match in BM25 (teams -> team, winning -> win)."""
    for suffix in ("ing", "ed", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix) and not word.endswith("ss"):
            word = word[:-len(suffix)]
            if suffix != "s" and word[-1] == word[-2] and word[-1] not in "lsz":  # winn -> win, submitt -> submit
                word = word[:-1]
            return word
    return word


def _tokens(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"\w+", text.lower()) if w not in _STOP]


def _ranks(scores) -> list[int]:
    """Passage indexes best first; ties keep passage order so results are stable."""
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


class Retriever:
    """Indexes are built once, in __init__."""

    def __init__(self, passages: list[Passage], titles: dict[str, str], embedder: SentenceTransformer):
        self.passages = passages
        self.embedder = embedder
        docs = [f"{titles[p.id]}. {p.text}" for p in passages]
        self.bm25 = BM25Okapi([_tokens(d) for d in docs])
        self.vectors = embedder.encode(docs, normalize_embeddings=True)
        sentences = [s for p in passages for s in p.sentences]
        vectors = embedder.encode([s.text for s in sentences], normalize_embeddings=True)
        self.sentence_vectors = {s.id: v for s, v in zip(sentences, vectors)}

    def related(self, text: str, sentence_ids: list[str], k: int) -> list[tuple[str, float]]:
        """The k sentences (of sentence_ids) most similar to text: (id, cosine), best first, ties in given order."""
        query = self.embedder.encode(text, normalize_embeddings=True)
        sims = [float(self.sentence_vectors[i] @ query) for i in sentence_ids]
        return [(sentence_ids[i], sims[i]) for i in _ranks(sims)[:k]]

    def search(self, query: str, top_k: int, rrf_k: int) -> list[Passage]:
        bm25_scores = self.bm25.get_scores(_tokens(query))
        dense_scores = self.vectors @ self.embedder.encode(query, normalize_embeddings=True)
        fused = [0.0] * len(self.passages)
        for ranking in (_ranks(bm25_scores), _ranks(dense_scores)):
            for rank, i in enumerate(ranking, 1):
                fused[i] += 1 / (rrf_k + rank)
        return [self.passages[i] for i in _ranks(fused)[:top_k]]
