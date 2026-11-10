"""Keyword retrieval with BM25. No embedding model needed.

Two uses:
1. rank_jobs: the resume is the query, the jobs are the corpus. Picks which jobs go to Claude.
2. retrieve_evidence: the job is the query, the resume chunks are the corpus. This is the
   retrieval step of the RAG flow: Claude only sees the chunks that matter for that job.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from jobmatch.models import Job, RankedJob

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.]*")
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it of on or our that the this to
    we will with you your they their about all can who what when where how not but if into
    us more than also other work working team role job years year""".split()
)


def tokenize(text: str) -> list[str]:
    tokens = (t.rstrip(".") for t in _TOKEN.findall(text.lower()))
    return [t for t in tokens if t and t not in _STOPWORDS and len(t) > 1 or t in {"c", "r"}]


class BM25:
    """Okapi BM25 over pre-tokenized documents."""

    def __init__(self, docs: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self._k1 = k1
        self._b = b
        self._tfs = [Counter(d) for d in docs]
        self._lens = [len(d) for d in docs]
        self._avg_len = (sum(self._lens) / len(docs)) if docs else 0.0
        df = Counter(term for d in docs for term in set(d))
        n = len(docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: Sequence[str]) -> list[float]:
        terms = set(query)  # unique terms, so a long resume does not repeat-boost a word
        return [self._score_doc(tf, length, terms) for tf, length in zip(self._tfs, self._lens)]

    def _score_doc(self, tf: Counter, length: int, terms: set[str]) -> float:
        total = 0.0
        norm = self._k1 * (1 - self._b + self._b * length / self._avg_len) if self._avg_len else self._k1
        for term in terms:
            f = tf.get(term)
            if f:
                total += self._idf[term] * f * (self._k1 + 1) / (f + norm)
        return total


def rank_jobs(resume_text: str, jobs: Sequence[Job]) -> list[RankedJob]:
    """Rank jobs by keyword overlap with the resume. Scores scale to 0..1."""
    if not jobs:
        return []
    raw = BM25([tokenize(j.search_text()) for j in jobs]).scores(tokenize(resume_text))
    best = max(raw) or 1.0
    ranked = [RankedJob(job=j, score=s / best) for j, s in zip(jobs, raw)]
    return sorted(ranked, key=lambda r: r.score, reverse=True)


def retrieve_evidence(chunks: Sequence[str], job_text: str, k: int) -> list[tuple[int, str]]:
    """Return up to k (index, chunk) pairs, best first. Chunks that score 0 are left out."""
    scores = BM25([tokenize(c) for c in chunks]).scores(tokenize(job_text))
    order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    return [(i, chunks[i]) for i in order[:k] if scores[i] > 0]
