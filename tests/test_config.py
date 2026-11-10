import os
from pathlib import Path

import pytest

from jobmatch.config import ConfigError, load_config, load_dotenv

EXAMPLE = Path(__file__).parent.parent / "config.example.toml"


def test_example_config_loads():
    cfg = load_config(EXAMPLE)

    assert cfg.search.queries
    assert cfg.rank.top_n == 10
    assert cfg.claude.model == "claude-opus-5-5"
    assert cfg.resume_path.is_absolute()  # ~ is expanded
    assert cfg.db_path.parent == EXAMPLE.parent  # relative paths follow the config file


def test_bad_values_raise(tmp_path):
    bad = EXAMPLE.read_text().replace('effort = "medium"', 'effort = "turbo"')
    path = tmp_path / "c.toml"
    path.write_text(bad)

    with pytest.raises(ConfigError, match="effort"):
        load_config(path)


def test_empty_queries_raise(tmp_path):
    text = EXAMPLE.read_text()
    start = text.index("queries = [")
    end = text.index("]", start) + 1
    path = tmp_path / "c.toml"
    path.write_text(text[:start] + "queries = []" + text[end:])

    with pytest.raises(ConfigError, match="queries"):
        load_config(path)


def test_missing_config_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "none.toml")


def test_load_dotenv_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nJM_A=from_file\nJM_B='quoted'\nJM_C=\n")
    monkeypatch.setenv("JM_A", "from_shell")
    monkeypatch.delenv("JM_B", raising=False)
    monkeypatch.delenv("JM_C", raising=False)

    load_dotenv(env)

    assert os.environ["JM_A"] == "from_shell"
    assert os.environ["JM_B"] == "quoted"
    assert "JM_C" not in os.environ  # empty values are skipped
