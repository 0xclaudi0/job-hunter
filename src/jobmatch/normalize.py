"""Turn raw SerpApi Google Jobs results into Job objects."""

from __future__ import annotations

import hashlib
import re

from jobmatch.models import Job

_COMPANY_SUFFIXES = re.compile(r"\b(inc|llc|ltd|limited|gmbh|corp|co)\b")
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    text = _NON_WORD.sub(" ", text.lower())
    return " ".join(text.split())


def dedupe_key(title: str, company: str) -> str:
    """Same role posted on LinkedIn and Indeed should produce the same key."""
    company_norm = " ".join(_COMPANY_SUFFIXES.sub(" ", _normalize(company)).split())
    raw = f"{_normalize(title)}|{company_norm}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _description(raw: dict) -> str:
    parts = [raw.get("description", "")]
    for block in raw.get("job_highlights") or []:
        items = block.get("items") or []
        if items:
            parts.append(f"{block.get('title', '')}: " + "; ".join(items))
    return "\n".join(p for p in parts if p).strip()


def job_from_serpapi(raw: dict, query: str) -> Job | None:
    """Return a Job, or None when the record has no title or company."""
    title = (raw.get("title") or "").strip()
    company = (raw.get("company_name") or "").strip()
    if not title or not company:
        return None

    ext = raw.get("detected_extensions") or {}
    links = tuple(
        opt["link"] for opt in raw.get("apply_options") or [] if isinstance(opt, dict) and opt.get("link")
    )
    return Job(
        key=dedupe_key(title, company),
        job_id=raw.get("job_id", ""),
        title=title,
        company=company,
        location=raw.get("location", ""),
        via=raw.get("via", ""),
        description=_description(raw),
        posted_at=ext.get("posted_at", ""),
        schedule_type=ext.get("schedule_type", ""),
        salary=ext.get("salary", ""),
        work_from_home=bool(ext.get("work_from_home", False)),
        apply_links=links,
        query=query,
    )


def jobs_from_page(page: dict, query: str) -> list[Job]:
    jobs = (job_from_serpapi(raw, query) for raw in page.get("jobs_results") or [])
    return [job for job in jobs if job is not None]
