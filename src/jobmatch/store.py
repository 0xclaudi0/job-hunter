"""SQLite storage: SerpApi cache, jobs, Claude analyses, letters and your feedback."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from jobmatch.models import Job

FEEDBACK_STATUSES = frozenset({"rejected", "applied", "saved"})
_KEY_PREFIX = re.compile(r"[0-9a-f]{4,40}")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS serp_cache (key TEXT PRIMARY KEY, fetched_at REAL NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
    key TEXT PRIMARY KEY, data TEXT NOT NULL, first_seen REAL NOT NULL, last_seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS analyses (
    job_key TEXT PRIMARY KEY, model TEXT NOT NULL, data TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS letters (job_key TEXT PRIMARY KEY, body TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (job_key TEXT PRIMARY KEY, status TEXT NOT NULL, at REAL NOT NULL);
"""


class Store:
    def __init__(self, path: Path | str, now: Callable[[], float] = time.time):
        self._now = now
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # --- SerpApi cache -------------------------------------------------------
    def get_cache(self, key: str, ttl_seconds: float) -> dict | None:
        row = self._conn.execute("SELECT fetched_at, body FROM serp_cache WHERE key = ?", (key,)).fetchone()
        if row is None or self._now() - row[0] > ttl_seconds:
            return None
        return json.loads(row[1])

    def put_cache(self, key: str, body: dict) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO serp_cache (key, fetched_at, body) VALUES (?, ?, ?)",
                (key, self._now(), json.dumps(body)),
            )

    # --- jobs ----------------------------------------------------------------
    def upsert_job(self, job: Job) -> None:
        now = self._now()
        with self._conn:
            self._conn.execute(
                """INSERT INTO jobs (key, data, first_seen, last_seen) VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET data = excluded.data, last_seen = excluded.last_seen""",
                (job.key, json.dumps(job.to_dict()), now, now),
            )

    def recent_jobs(self, max_age_seconds: float) -> list[Job]:
        cutoff = self._now() - max_age_seconds
        rows = self._conn.execute("SELECT data FROM jobs WHERE last_seen >= ?", (cutoff,)).fetchall()
        return [Job.from_dict(json.loads(r[0])) for r in rows]

    def find_job(self, key_prefix: str) -> Job | None:
        """Find a job by the start of its key. Keys are hex, so LIKE wildcards never get through."""
        if not _KEY_PREFIX.fullmatch(key_prefix.lower()):
            return None
        rows = self._conn.execute(
            "SELECT data FROM jobs WHERE key LIKE ? LIMIT 2", (key_prefix.lower() + "%",)
        ).fetchall()
        return Job.from_dict(json.loads(rows[0][0])) if len(rows) == 1 else None

    # --- analyses and letters ------------------------------------------------
    def get_analysis(self, job_key: str) -> dict | None:
        row = self._conn.execute("SELECT data FROM analyses WHERE job_key = ?", (job_key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_analysis(self, job_key: str, model: str, data: dict) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO analyses (job_key, model, data, created_at) VALUES (?, ?, ?, ?)",
                (job_key, model, json.dumps(data), self._now()),
            )

    def get_letter(self, job_key: str) -> str | None:
        row = self._conn.execute("SELECT body FROM letters WHERE job_key = ?", (job_key,)).fetchone()
        return row[0] if row else None

    def put_letter(self, job_key: str, body: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO letters (job_key, body, created_at) VALUES (?, ?, ?)",
                (job_key, body, self._now()),
            )

    # --- feedback ------------------------------------------------------------
    def set_feedback(self, job_key: str, status: str) -> None:
        if status not in FEEDBACK_STATUSES:
            raise ValueError(f"status must be one of {sorted(FEEDBACK_STATUSES)}, not {status!r}")
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO feedback (job_key, status, at) VALUES (?, ?, ?)",
                (job_key, status, self._now()),
            )

    def feedback(self) -> dict[str, str]:
        return dict(self._conn.execute("SELECT job_key, status FROM feedback").fetchall())
