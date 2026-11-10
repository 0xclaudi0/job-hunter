from dataclasses import replace
from pathlib import Path

import pytest

from conftest import FIXTURES, FakeClaude, FakeHttp
from jobmatch.config import load_config
from jobmatch.pipeline import run_pipeline
from jobmatch.serpapi_client import GoogleJobsClient
from jobmatch.store import Store

EXAMPLE = Path(__file__).parent.parent / "config.example.toml"


@pytest.fixture
def cfg(tmp_path):
    base = load_config(EXAMPLE)
    return replace(
        base,
        resume_path=FIXTURES / "resume.txt",
        db_path=tmp_path / "jobs.db",
        output_dir=tmp_path / "out",
        search=replace(base.search, queries=("WordPress developer",), max_pages=2),
        rank=replace(base.rank, top_n=2),
    )


@pytest.fixture
def store(cfg):
    s = Store(cfg.db_path)
    yield s
    s.close()


def test_pipeline_dedupes_filters_ranks_and_analyzes(cfg, store, page1, page2, good_analysis_json):
    serp = GoogleJobsClient("KEY", http_get=FakeHttp([(200, page1), (200, page2)]), store=store)
    claude = FakeClaude([good_analysis_json])

    report = run_pipeline(cfg, serp, store, claude)

    assert report.fetched == 5  # 3 + 2 valid records over two pages
    assert report.stored == 4  # the Acme duplicate merges
    titles = [r.job.title for r in report.results]
    assert "Sales Development Representative" not in titles  # title filter
    assert len(report.results) == 2  # top_n
    assert len(claude.calls) == 2
    assert all(r.analysis is not None for r in report.results)
    assert report.results[0].analysis.fit_score >= report.results[1].analysis.fit_score


def test_pipeline_reuses_analysis_and_skips_rejected(cfg, store, page1, page2, good_analysis_json):
    serp = GoogleJobsClient("KEY", http_get=FakeHttp([(200, page1), (200, page2)]), store=store)
    claude = FakeClaude([good_analysis_json])
    first = run_pipeline(cfg, serp, store, claude)
    rejected = first.results[0].job
    store.set_feedback(rejected.key, "rejected")

    second = run_pipeline(cfg, serp, store, claude)  # SerpApi answers come from cache

    assert rejected.key not in [r.job.key for r in second.results]
    assert len(claude.calls) == 3  # only the one new job in the top 2 needed Claude


def test_pipeline_without_claude_returns_ranked_jobs(cfg, store, page1, page2):
    serp = GoogleJobsClient("KEY", http_get=FakeHttp([(200, page1), (200, page2)]), store=store)

    report = run_pipeline(cfg, serp, store, None)

    assert len(report.results) == 2
    assert all(r.analysis is None for r in report.results)


def test_pipeline_keeps_going_when_one_analysis_fails(cfg, store, page1, page2, good_analysis_json):
    serp = GoogleJobsClient("KEY", http_get=FakeHttp([(200, page1), (200, page2)]), store=store)
    claude = FakeClaude(["not json", good_analysis_json])

    report = run_pipeline(cfg, serp, store, claude)

    assert len(report.errors) == 1
    assert sum(r.analysis is not None for r in report.results) == 1
