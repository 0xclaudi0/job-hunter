from urllib.parse import parse_qs, urlparse

import pytest

from conftest import FakeHttp
from jobmatch.serpapi_client import GoogleJobsClient, SerpApiError
from jobmatch.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def params_of(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_search_follows_next_page_token(page1, page2):
    http = FakeHttp([(200, page1), (200, page2)])
    client = GoogleJobsClient("KEY", http_get=http)

    results = client.search("WordPress developer", remote_only=True, max_pages=3)

    assert len(results) == 6  # 4 + 2; page 2 has no next token, so it stops
    first, second = params_of(http.urls[0]), params_of(http.urls[1])
    assert first["engine"] == "google_jobs"
    assert first["ltype"] == "1"
    assert "next_page_token" not in first
    assert second["next_page_token"] == "TOKEN_PAGE_2"


def test_search_uses_cache_and_keeps_api_key_out_of_it(store, page2):
    http = FakeHttp([(200, page2)])
    client = GoogleJobsClient("SECRET", http_get=http, store=store)

    client.search("support", max_pages=1)
    again = client.search("support", max_pages=1)

    assert len(http.urls) == 1
    assert len(again) == 2
    rows = store._conn.execute("SELECT key, body FROM serp_cache").fetchall()
    assert all("SECRET" not in key + body for key, body in rows)


def test_location_is_sent_only_when_set(page2):
    http = FakeHttp([(200, page2), (200, page2)])
    client = GoogleJobsClient("KEY", http_get=http)

    client.search("q", location="")
    client.search("q", location="United Kingdom")

    assert "location" not in params_of(http.urls[0])
    assert params_of(http.urls[1])["location"] == "United Kingdom"


def test_no_results_message_is_an_empty_list():
    body = {"error": "Google hasn't returned any results for this query."}
    client = GoogleJobsClient("KEY", http_get=FakeHttp([(200, body)]))

    assert client.search("very rare job") == []


@pytest.mark.parametrize(
    "status, body, text",
    [
        (401, {"error": "Invalid API key."}, "API key"),
        (429, {"error": "Your account has run out of searches."}, "run out of searches"),
        (500, {"error": "boom"}, "boom"),
        (200, {"error": "Unsupported parameter"}, "Unsupported parameter"),
    ],
)
def test_errors_raise_serpapi_error(status, body, text):
    client = GoogleJobsClient("KEY", http_get=FakeHttp([(status, body)]))

    with pytest.raises(SerpApiError, match=text):
        client.search("q")


def test_empty_api_key_is_rejected():
    with pytest.raises(SerpApiError, match="SERPAPI_API_KEY"):
        GoogleJobsClient("")
