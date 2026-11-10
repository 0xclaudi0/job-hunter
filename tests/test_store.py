import pytest

from jobmatch.normalize import jobs_from_page
from jobmatch.store import Store


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    s = Store(tmp_path / "test.db", now=clock)
    yield s
    s.close()


def test_cache_returns_body_inside_ttl_only(store, clock):
    store.put_cache("k", {"a": 1})

    assert store.get_cache("k", ttl_seconds=60) == {"a": 1}
    clock.t += 61
    assert store.get_cache("k", ttl_seconds=60) is None


def test_upsert_job_is_idempotent_and_updates_last_seen(store, clock, page1):
    job = jobs_from_page(page1, query="q")[0]

    store.upsert_job(job)
    clock.t += 100
    store.upsert_job(job)

    jobs = store.recent_jobs(max_age_seconds=50)
    assert len(jobs) == 1
    assert jobs[0].key == job.key


def test_recent_jobs_drops_stale_jobs(store, clock, page1):
    store.upsert_job(jobs_from_page(page1, query="q")[0])
    clock.t += 1000

    assert store.recent_jobs(max_age_seconds=500) == []


def test_find_job_by_key_prefix(store, page1):
    job = jobs_from_page(page1, query="q")[0]
    store.upsert_job(job)

    assert store.find_job(job.key[:8]).title == job.title
    assert store.find_job(job.key[:8].upper()).title == job.title
    assert store.find_job("zzzz") is None
    assert store.find_job("%") is None  # a LIKE wildcard must not match every job
    assert store.find_job("ab") is None  # too short to be useful


def test_feedback_roundtrip_and_validation(store):
    store.set_feedback("abc", "rejected")
    store.set_feedback("def", "applied")
    store.set_feedback("abc", "saved")  # last status wins

    assert store.feedback() == {"abc": "saved", "def": "applied"}
    with pytest.raises(ValueError):
        store.set_feedback("abc", "maybe")


def test_analysis_and_letter_roundtrip(store):
    store.put_analysis("abc", "model-x", {"fit_score": 50})
    store.put_letter("abc", "Dear team")

    assert store.get_analysis("abc") == {"fit_score": 50}
    assert store.get_analysis("missing") is None
    assert store.get_letter("abc") == "Dear team"
