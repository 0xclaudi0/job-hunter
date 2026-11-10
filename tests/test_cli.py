from pathlib import Path

import pytest

from conftest import FIXTURES, FakeClaude, FakeHttp
from jobmatch import cli
from jobmatch.serpapi_client import GoogleJobsClient

EXAMPLE = Path(__file__).parent.parent / "config.example.toml"


@pytest.fixture
def setup(tmp_path, monkeypatch, page1, page2, good_analysis_json):
    text = EXAMPLE.read_text().replace('"~/Desktop/resume.pdf"', f'"{FIXTURES / "resume.txt"}"')
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(text)
    claude = FakeClaude([good_analysis_json])

    def fake_serp(cfg, store):
        return GoogleJobsClient("KEY", http_get=FakeHttp([(200, page1), (200, page2)] * 5), store=store)

    monkeypatch.setattr(cli, "make_serp", fake_serp)
    monkeypatch.setattr(cli, "make_claude", lambda: claude)
    base = ["--config", str(cfg_path), "--env", str(tmp_path / "none.env")]
    return base, tmp_path, claude


def first_key(output: str) -> str:
    rows = output.split("COMPANY\n", 1)[1].splitlines()
    return rows[0].split()[0]


def test_run_prints_table_and_writes_report(setup, capsys):
    base, tmp_path, _ = setup

    assert cli.main(base + ["run"]) == 0

    out = capsys.readouterr().out
    assert "WordPress Developer" in out
    reports = list((tmp_path / "output").glob("matches-*.md"))
    assert len(reports) == 1
    assert "Fit 82/100" in reports[0].read_text()


def test_show_mark_and_letter(setup, capsys):
    base, tmp_path, claude = setup
    cli.main(base + ["run", "--no-llm"])
    key = first_key(capsys.readouterr().out)

    assert cli.main(base + ["show", key]) == 0
    assert "No Claude analysis yet" in capsys.readouterr().out

    claude.replies = [claude.replies[0], "Dear team,\n\nDraft letter."]
    assert cli.main(base + ["letter", key]) == 0
    assert "Draft letter." in capsys.readouterr().out
    assert len(list((tmp_path / "output" / "letters").glob("*.txt"))) == 1

    assert cli.main(base + ["mark", key, "applied"]) == 0
    assert "as applied" in capsys.readouterr().out


def test_unknown_key_and_bad_config_return_errors(setup, tmp_path, capsys):
    base, _, _ = setup

    assert cli.main(base + ["show", "ffffffff"]) == 1
    assert "No single job" in capsys.readouterr().err
    assert cli.main(["--config", str(tmp_path / "missing.toml"), "run"]) == 1
    assert "Config not found" in capsys.readouterr().err
