import json
from pathlib import Path
from types import SimpleNamespace

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class FakeHttp:
    """Stands in for the SerpApi HTTP call. Returns queued (status, body) pairs."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def __call__(self, url: str):
        self.urls.append(url)
        if not self.responses:
            raise AssertionError(f"unexpected request: {url}")
        return self.responses.pop(0)


class FakeClaude:
    """Stands in for anthropic.Anthropic(). Records each beta.messages.create call."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, SimpleNamespace):
            return reply
        return text_response(reply)


def text_response(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=None,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
    )


GOOD_ANALYSIS = {
    "fit_score": 82,
    "verdict": "strong",
    "summary": "Close match on WordPress and support work.",
    "requirements": ["WordPress and WooCommerce", "PHP"],
    "matches": [{"requirement": "WordPress and WooCommerce", "evidence_chunk": 1}],
    "gaps": ["No agency experience shown"],
    "red_flags": [],
}


@pytest.fixture
def page1():
    return load_fixture("google_jobs_page1.json")


@pytest.fixture
def page2():
    return load_fixture("google_jobs_page2.json")


@pytest.fixture
def resume_text():
    return (FIXTURES / "resume.txt").read_text()


@pytest.fixture
def good_analysis_json():
    return json.dumps(GOOD_ANALYSIS)
