import json
from types import SimpleNamespace

import pytest

from conftest import GOOD_ANALYSIS, FakeClaude, text_response
from jobmatch.analyze import analyze_job
from jobmatch.letters import write_cover_letter
from jobmatch.llm import ClaudeError
from jobmatch.normalize import jobs_from_page

EVIDENCE = [(1, "Built WordPress and WooCommerce sites.")]


@pytest.fixture
def job(page1):
    return jobs_from_page(page1, query="q")[0]


def test_analyze_job_parses_structured_reply(job, good_analysis_json):
    claude = FakeClaude([good_analysis_json])

    result = analyze_job(claude, "claude-opus-5-5", "medium", job, EVIDENCE, "Remote only.")

    assert result.fit_score == 82
    assert result.verdict == "strong"
    call = claude.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in call["betas"]
    assert call["output_config"]["effort"] == "medium"
    assert call["output_config"]["format"]["type"] == "json_schema"
    prompt = call["messages"][0]["content"]
    assert "[chunk 1]" in prompt and "WordPress Developer" in prompt


def test_analyze_job_drops_citations_to_unknown_chunks(job):
    reply = dict(GOOD_ANALYSIS, matches=[
        {"requirement": "PHP", "evidence_chunk": 99},
        {"requirement": "WordPress", "evidence_chunk": 1},
    ])
    claude = FakeClaude([json.dumps(reply)])

    result = analyze_job(claude, "m", "low", job, EVIDENCE, "")

    assert [m.evidence_chunk for m in result.matches] == [1]


@pytest.mark.parametrize(
    "reply, message",
    [
        (text_response("{}", stop_reason="refusal"), "declined"),
        (text_response("{\"fit", stop_reason="max_tokens"), "max_tokens"),
        (text_response("not json"), "JSON"),
        (text_response(json.dumps(dict(GOOD_ANALYSIS, fit_score=140))), "fit_score"),
        (SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[]), "no text"),
    ],
)
def test_analyze_job_errors(job, reply, message):
    with pytest.raises(ClaudeError, match=message):
        analyze_job(FakeClaude([reply]), "m", "low", job, EVIDENCE, "")


def test_write_cover_letter_returns_text(job):
    claude = FakeClaude(["Dear Acme team,\n\nI build WordPress sites."])
    analysis = analyze_job(FakeClaude([json.dumps(GOOD_ANALYSIS)]), "m", "low", job, EVIDENCE, "")

    letter = write_cover_letter(claude, "m", "medium", job, analysis, EVIDENCE, "Jane Tester", "Remote only.")

    assert letter.startswith("Dear Acme team")
    prompt = claude.calls[0]["messages"][0]["content"]
    assert "Jane Tester" in prompt and "No agency experience shown" in prompt
    assert "output_config" in claude.calls[0] and "format" not in claude.calls[0]["output_config"]
