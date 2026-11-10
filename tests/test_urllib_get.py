import io
import urllib.error

import pytest

from jobmatch import serpapi_client
from jobmatch.serpapi_client import SerpApiError, urllib_get


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_urllib_get_parses_json(monkeypatch):
    monkeypatch.setattr(serpapi_client.urllib.request, "urlopen", lambda req, timeout: FakeResponse(b'{"ok": 1}'))

    assert urllib_get("https://serpapi.com/search.json") == (200, {"ok": 1})


def test_urllib_get_returns_error_body_for_http_errors(monkeypatch):
    def raise_http(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error": "Invalid API key."}'))

    monkeypatch.setattr(serpapi_client.urllib.request, "urlopen", raise_http)

    assert urllib_get("https://x") == (401, {"error": "Invalid API key."})


def test_urllib_get_handles_html_error_page(monkeypatch):
    def raise_http(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, io.BytesIO(b"<html>"))

    monkeypatch.setattr(serpapi_client.urllib.request, "urlopen", raise_http)

    assert urllib_get("https://x") == (502, {"error": "HTTP 502"})


@pytest.mark.parametrize(
    "behavior, message",
    [
        (lambda req, timeout: FakeResponse(b"<html>not json"), "not JSON"),
        (lambda req, timeout: (_ for _ in ()).throw(urllib.error.URLError("offline")), "Could not reach"),
    ],
)
def test_urllib_get_wraps_failures(monkeypatch, behavior, message):
    monkeypatch.setattr(serpapi_client.urllib.request, "urlopen", behavior)

    with pytest.raises(SerpApiError, match=message):
        urllib_get("https://x")
