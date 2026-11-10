"""Load and check config.toml and .env."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
MAX_TOP_N = 50


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SearchConfig:
    queries: tuple[str, ...]
    location: str
    remote_only: bool
    max_pages: int
    cache_ttl_hours: float


@dataclass(frozen=True)
class FilterConfig:
    exclude_title_words: tuple[str, ...]
    max_age_days: float


@dataclass(frozen=True)
class RankConfig:
    top_n: int
    evidence_chunks: int


@dataclass(frozen=True)
class ClaudeConfig:
    model: str
    effort: str


@dataclass(frozen=True)
class CandidateConfig:
    name: str
    notes: str


@dataclass(frozen=True)
class Config:
    resume_path: Path
    db_path: Path
    output_dir: Path
    search: SearchConfig
    filter: FilterConfig
    rank: RankConfig
    claude: ClaudeConfig
    candidate: CandidateConfig


def _path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def load_config(path: Path | str) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config not found: {path}. Copy config.example.toml to config.toml.")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"{path} is not valid TOML: {err}") from err

    base = path.parent.resolve()
    s, f, r, c, cand = (raw.get(k, {}) for k in ("search", "filter", "rank", "claude", "candidate"))
    queries = tuple(q.strip() for q in s.get("queries", []) if q.strip())

    cfg = Config(
        resume_path=_path(raw.get("resume_path", "resume.pdf"), base),
        db_path=_path(raw.get("db_path", "jobs.db"), base),
        output_dir=_path(raw.get("output_dir", "output"), base),
        search=SearchConfig(
            queries=queries,
            location=s.get("location", ""),
            remote_only=bool(s.get("remote_only", True)),
            max_pages=int(s.get("max_pages", 1)),
            cache_ttl_hours=float(s.get("cache_ttl_hours", 20)),
        ),
        filter=FilterConfig(
            exclude_title_words=tuple(w.lower() for w in f.get("exclude_title_words", [])),
            max_age_days=float(f.get("max_age_days", 14)),
        ),
        rank=RankConfig(top_n=int(r.get("top_n", 10)), evidence_chunks=int(r.get("evidence_chunks", 4))),
        claude=ClaudeConfig(model=c.get("model", "claude-opus-5-5"), effort=c.get("effort", "medium")),
        candidate=CandidateConfig(name=cand.get("name", ""), notes=cand.get("notes", "")),
    )

    _require(bool(cfg.search.queries), "search.queries must list at least one query")
    _require(1 <= cfg.search.max_pages <= 10, "search.max_pages must be 1-10")
    _require(1 <= cfg.rank.top_n <= MAX_TOP_N, f"rank.top_n must be 1-{MAX_TOP_N}")
    _require(1 <= cfg.rank.evidence_chunks <= 20, "rank.evidence_chunks must be 1-20")
    _require(cfg.claude.effort in EFFORTS, f"claude.effort must be one of {sorted(EFFORTS)}")
    return cfg


def load_dotenv(path: Path | str) -> None:
    """Read KEY=VALUE lines. Values already in the environment win. Empty values are skipped."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if value and key not in os.environ:
            os.environ[key] = value
