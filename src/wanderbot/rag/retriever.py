"""Hybrid retriever (lexical + optional vector) with citation tracking.

Combines a BM25-style lexical score with optional embedding cosine similarity
(reciprocal-rank fusion). Every chunk carries a ``source`` so the research agent's
claims remain traceable.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from wanderbot.memory.store import EmbedderProto, _cosine

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


@dataclass
class Document:
    text: str
    source: str


@dataclass
class Retrieved:
    text: str
    source: str
    score: float


class HybridRetriever:
    def __init__(self, docs: list[Document], embedder: EmbedderProto | None = None):
        self._docs = docs
        self._embedder = embedder
        self._embeddings: list[list[float]] | None = None
        # Precompute IDF for the lexical scorer.
        self._df: Counter[str] = Counter()
        for d in docs:
            for tok in set(_tokens(d.text)):
                self._df[tok] += 1
        self._n = max(len(docs), 1)

    async def aindex(self) -> None:
        if self._embedder is not None and self._embeddings is None:
            self._embeddings = await self._embedder.aembed([d.text for d in self._docs])

    def _bm25ish(self, query: str) -> list[float]:
        q = _tokens(query)
        scores = []
        for d in self._docs:
            toks = _tokens(d.text)
            tf = Counter(toks)
            score = 0.0
            for term in q:
                if term in tf:
                    idf = math.log(1 + self._n / (1 + self._df[term]))
                    score += idf * (tf[term] / (len(toks) or 1))
            scores.append(score)
        return scores

    async def retrieve(self, query: str, k: int = 4) -> list[Retrieved]:
        lexical = self._bm25ish(query)
        ranks: list[tuple[int, float]] = []

        if self._embedder is not None:
            await self.aindex()
            qv = (await self._embedder.aembed([query]))[0]
            vec = [_cosine(qv, e) for e in (self._embeddings or [])]
            # Reciprocal-rank fusion of the two orderings.
            lex_order = sorted(range(len(lexical)), key=lambda i: lexical[i], reverse=True)
            vec_order = sorted(range(len(vec)), key=lambda i: vec[i], reverse=True)
            rrf: dict[int, float] = {}
            for order in (lex_order, vec_order):
                for rank, idx in enumerate(order):
                    rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (60 + rank)
            ranks = sorted(rrf.items(), key=lambda x: x[1], reverse=True)
        else:
            ranks = sorted(enumerate(lexical), key=lambda x: x[1], reverse=True)

        out: list[Retrieved] = []
        for idx, score in ranks[:k]:
            if score <= 0:
                continue
            d = self._docs[idx]
            out.append(Retrieved(text=d.text, source=d.source, score=float(score)))
        return out
