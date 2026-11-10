"""Data types shared across the pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Job:
    """One job post, normalized from a SerpApi Google Jobs result."""

    key: str  # dedupe key: same title + company on two job boards -> same key
    job_id: str
    title: str
    company: str
    location: str
    via: str
    description: str
    posted_at: str
    schedule_type: str
    salary: str
    work_from_home: bool
    apply_links: tuple[str, ...]
    query: str

    @property
    def short_key(self) -> str:
        return self.key[:8]

    def search_text(self) -> str:
        return f"{self.title}\n{self.company}\n{self.description}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        return cls(**{**data, "apply_links": tuple(data.get("apply_links", ()))})


class Match(BaseModel, frozen=True):
    requirement: str
    evidence_chunk: int


class JobAnalysis(BaseModel, frozen=True):
    """Claude's verdict on one job. Every match must cite a resume chunk."""

    fit_score: int = Field(ge=0, le=100)
    verdict: Literal["strong", "possible", "weak"]
    summary: str
    requirements: tuple[str, ...]
    matches: tuple[Match, ...]
    gaps: tuple[str, ...]
    red_flags: tuple[str, ...]


@dataclass(frozen=True)
class RankedJob:
    job: Job
    score: float  # BM25 score scaled to 0..1 against the best job in the run
    analysis: JobAnalysis | None = None
