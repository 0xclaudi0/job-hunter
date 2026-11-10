"""Command line entry point: jobmatch run | show | letter | mark."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

from jobmatch import report as render
from jobmatch.analyze import analyze_job
from jobmatch.config import Config, ConfigError, load_config, load_dotenv
from jobmatch.letters import write_cover_letter
from jobmatch.llm import ClaudeClient, ClaudeError
from jobmatch.models import Job, JobAnalysis, RankedJob
from jobmatch.pipeline import run_pipeline
from jobmatch.rank import retrieve_evidence
from jobmatch.resume import ResumeError, chunk_resume, load_resume_text
from jobmatch.serpapi_client import GoogleJobsClient, SerpApiError
from jobmatch.store import FEEDBACK_STATUSES, Store


def make_claude() -> ClaudeClient:
    import anthropic  # imported here so --no-llm runs never need it configured

    return anthropic.Anthropic()


def make_serp(cfg: Config, store: Store) -> GoogleJobsClient:
    return GoogleJobsClient(
        os.environ.get("SERPAPI_API_KEY", ""), store=store, cache_ttl_hours=cfg.search.cache_ttl_hours
    )


def _find(store: Store, key: str) -> Job:
    job = store.find_job(key)
    if job is None:
        raise LookupError(f"No single job matches key {key!r}. Use the KEY column from `jobmatch run`.")
    return job


def cmd_run(cfg: Config, store: Store, args: argparse.Namespace) -> int:
    claude = None if args.no_llm else make_claude()
    result = run_pipeline(cfg, make_serp(cfg, store), store, claude)
    print(render.table(result))
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.output_dir / f"matches-{date.today().isoformat()}.md"
    path.write_text(render.markdown(result, date.today()), encoding="utf-8")
    print(f"\nReport: {path}")
    return 0


def cmd_show(cfg: Config, store: Store, args: argparse.Namespace) -> int:
    job = _find(store, args.key)
    cached = store.get_analysis(job.key)
    analysis = JobAnalysis.model_validate(cached) if cached else None
    print(render.job_detail(RankedJob(job=job, score=0.0, analysis=analysis)))
    print(f"\n{job.description}")
    return 0


def cmd_letter(cfg: Config, store: Store, args: argparse.Namespace) -> int:
    job = _find(store, args.key)
    claude = make_claude()
    chunks = chunk_resume(load_resume_text(cfg.resume_path))
    evidence = retrieve_evidence(chunks, job.search_text(), cfg.rank.evidence_chunks)
    cached = store.get_analysis(job.key)
    if cached:
        analysis = JobAnalysis.model_validate(cached)
    else:
        analysis = analyze_job(claude, cfg.claude.model, cfg.claude.effort, job, evidence, cfg.candidate.notes)
        store.put_analysis(job.key, cfg.claude.model, analysis.model_dump(mode="json"))

    letter = write_cover_letter(
        claude, cfg.claude.model, cfg.claude.effort, job, analysis, evidence, cfg.candidate.name, cfg.candidate.notes
    )
    store.put_letter(job.key, letter)
    slug = re.sub(r"[^a-z0-9]+", "-", job.company.lower()).strip("-")[:40] or "company"
    folder = cfg.output_dir / "letters"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slug}-{job.short_key}.txt"
    path.write_text(letter + "\n", encoding="utf-8")
    print(letter)
    print(f"\nSaved: {path}\nThis is a draft. Read it and edit it before you send it.")
    return 0


def cmd_mark(cfg: Config, store: Store, args: argparse.Namespace) -> int:
    job = _find(store, args.key)
    store.set_feedback(job.key, args.status)
    print(f"Marked {job.short_key} ({job.title} at {job.company}) as {args.status}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobmatch", description=__doc__)
    parser.add_argument("--config", default="config.toml", help="path to config.toml")
    parser.add_argument("--env", default=".env", help="path to a .env file with API keys")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="search, rank and analyze jobs")
    run.add_argument("--no-llm", action="store_true", help="skip Claude; BM25 ranking only")
    run.set_defaults(func=cmd_run)

    for name, func, text in [("show", cmd_show, "show one job"), ("letter", cmd_letter, "draft a cover letter")]:
        p = sub.add_parser(name, help=text)
        p.add_argument("key")
        p.set_defaults(func=func)

    mark = sub.add_parser("mark", help="record what you did with a job")
    mark.add_argument("key")
    mark.add_argument("status", choices=sorted(FEEDBACK_STATUSES))
    mark.set_defaults(func=cmd_mark)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    try:
        load_dotenv(Path(args.env))
        cfg = load_config(args.config)
        cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
        store = Store(cfg.db_path)
        try:
            return args.func(cfg, store, args)
        finally:
            store.close()
    except (ConfigError, ResumeError, SerpApiError, ClaudeError, LookupError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
