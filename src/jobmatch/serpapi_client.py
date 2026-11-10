"""SerpApi Google Jobs client with pagination and a local SQLite cache."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlencode

from jobmatch.store import Store

log = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
REQUEST_TIMEOUT_SECONDS = 60
_NO_RESULTS = "hasn't returned any results"

HttpGet = Callable[[str], tuple[int, dict]]


class SerpApiError(RuntimeError):
    pass


def urllib_get(url: str) -> tuple[int, dict]:
    """GET a URL and return (status, parsed JSON). SerpApi sends JSON on errors too."""
    request = urllib.request.Request(url, headers={"User-Agent": "job-hunter/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        try:
            body = json.loads(err.read())
        except (json.JSONDecodeError, ValueError):
            body = {"error": f"HTTP {err.code}"}
        return err.code, body
    except urllib.error.URLError as err:
        raise SerpApiError(f"Could not reach SerpApi: {err.reason}") from err
    except (json.JSONDecodeError, ValueError) as err:
        raise SerpApiError(f"SerpApi sent a reply that is not JSON: {err}") from err


def _explain(status: int, message: str) -> str:
    if status == 401:
        return f"SerpApi rejected the API key. Check SERPAPI_API_KEY. ({message})"
    if status == 429:
        return f"SerpApi limit reached: {message}"
    return f"SerpApi error (HTTP {status}): {message}"


class GoogleJobsClient:
    def __init__(
        self,
        api_key: str,
        http_get: HttpGet = urllib_get,
        store: Store | None = None,
        cache_ttl_hours: float = 20,
    ):
        if not api_key:
            raise SerpApiError("SERPAPI_API_KEY is not set. Add it to .env or your shell.")
        self._api_key = api_key
        self._http_get = http_get
        self._store = store
        self._ttl_seconds = cache_ttl_hours * 3600

    def search(
        self, query: str, location: str = "", remote_only: bool = True, max_pages: int = 1
    ) -> list[dict]:
        """Return raw job results for a query, following next_page_token up to max_pages."""
        params: dict[str, str] = {"engine": "google_jobs", "q": query, "hl": "en"}
        if location:
            params["location"] = location
        if remote_only:
            params["ltype"] = "1"

        results: list[dict] = []
        for _ in range(max_pages):
            page = self._fetch(params)
            results.extend(page.get("jobs_results") or [])
            token = (page.get("serpapi_pagination") or {}).get("next_page_token")
            if not token:
                break
            params = {**params, "next_page_token": token}
        return results

    def _fetch(self, params: dict[str, str]) -> dict:
        cache_key = json.dumps(params, sort_keys=True)  # the API key is never part of it
        if self._store is not None:
            cached = self._store.get_cache(cache_key, self._ttl_seconds)
            if cached is not None:
                log.debug("cache hit: %s", cache_key)
                return cached

        url = f"{SERPAPI_URL}?{urlencode({**params, 'api_key': self._api_key})}"
        status, body = self._http_get(url)
        error = body.get("error") if isinstance(body, dict) else "response was not JSON"
        if error and _NO_RESULTS in error:
            body = {"jobs_results": []}
        elif status != 200 or error:
            raise SerpApiError(_explain(status, error or "no error message"))

        if self._store is not None:
            self._store.put_cache(cache_key, body)
        return body
