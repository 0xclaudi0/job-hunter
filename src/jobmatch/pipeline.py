"""Search -> normalize -> dedupe -> filter -> rank -> retrieve evidence -> analyze."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from jobmatch.analyze import analyze_job
from jobmatch.config import Config
from jobmatch.llm import ClaudeClient, ClaudeError
from jobmatch.models import Job, JobAnalysis, RankedJob
from jobmatch.normalize import jobs_from_page
from jobmatch.rank import rank_jobs, retrieve_evidence
from jobmatch.resume import chunk_resume, load_resume_text
from jobmatch.serpapi_client import GoogleJobsClient
from jobmatch.store import Store

log = logging.getLogger(__name__)
SECONDS_PER_DAY = 86400
HIDDEN_STATUSES = frozenset({"rejected", "applied"})


@dataclass(frozen=True)
class RunReport:
    fetched: int
    stored: int
    results: tuple[RankedJob, ...]
    errors: tuple[str, ...]


def collect_jobs(cfg: Config, serp: GoogleJobsClient, store: Store) -> int:
    """Run every query and store the jobs. Return how many valid job records came back."""
    fetched = 0
    for query in cfg.search.queries:
        raw = serp.search(query, cfg.search.location, cfg.search.remote_only, cfg.search.max_pages)
        jobs = jobs_from_page({"jobs_results": raw}, query)
        fetched += len(jobs)
        for job in jobs:
            store.upsert_job(job)
    return fetched


def eligible(job: Job, cfg: Config, feedback: dict[str, str]) -> bool:
    title = job.title.lower()
    if feedback.get(job.key) in HIDDEN_STATUSES:
        return False
    return not any(word in title for word in cfg.filter.exclude_title_words)


def _analysis_for(
    job: Job, cfg: Config, store: Store, claude: ClaudeClient, chunks: tuple[str, ...]
) -> JobAnalysis:
    cached = store.get_analysis(job.key)
    if cached is not None:
        return JobAnalysis.model_validate(cached)
    evidence = retrieve_evidence(chunks, job.search_text(), cfg.rank.evidence_chunks)
    analysis = analyze_job(claude, cfg.claude.model, cfg.claude.effort, job, evidence, cfg.candidate.notes)
    store.put_analysis(job.key, cfg.claude.model, analysis.model_dump(mode="json"))
    return analysis


def _sort_key(r: RankedJob) -> tuple[int, float]:
    return (r.analysis.fit_score if r.analysis else -1, r.score)


def run_pipeline(
    cfg: Config, serp: GoogleJobsClient, store: Store, claude: ClaudeClient | None
) -> RunReport:
    resume_text = load_resume_text(cfg.resume_path)
    fetched = collect_jobs(cfg, serp, store)

    feedback = store.feedback()
    stored = store.recent_jobs(cfg.filter.max_age_days * SECONDS_PER_DAY)
    candidates = [j for j in stored if eligible(j, cfg, feedback)]
    top = rank_jobs(resume_text, candidates)[: cfg.rank.top_n]

    if claude is None:
        return RunReport(fetched, len(stored), tuple(top), ())

    chunks = chunk_resume(resume_text)
    results: list[RankedJob] = []
    errors: list[str] = []
    for ranked in top:
        try:
            results.append(replace(ranked, analysis=_analysis_for(ranked.job, cfg, store, claude, chunks)))
        except ClaudeError as err:
            log.warning("analysis failed for %s: %s", ranked.job.short_key, err)
            errors.append(f"{ranked.job.short_key} {ranked.job.title}: {err}")
            results.append(ranked)

    ordered = tuple(sorted(results, key=_sort_key, reverse=True))
    return RunReport(fetched, len(stored), ordered, tuple(errors))
