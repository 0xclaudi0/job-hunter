"""Render results as a terminal table and as a Markdown report."""

from __future__ import annotations

from datetime import date

from jobmatch.models import RankedJob
from jobmatch.pipeline import RunReport

TITLE_WIDTH = 42
COMPANY_WIDTH = 22


def _cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def table(report: RunReport) -> str:
    lines = [
        f"{report.fetched} jobs fetched, {report.stored} stored. Top {len(report.results)}:",
        "",
        f"{'KEY':8}  {'FIT':>3}  {'BM25':>4}  {'TITLE':{TITLE_WIDTH}}  COMPANY",
    ]
    for r in report.results:
        fit = str(r.analysis.fit_score) if r.analysis else "-"
        lines.append(
            f"{r.job.short_key:8}  {fit:>3}  {r.score:4.2f}  "
            f"{_cut(r.job.title, TITLE_WIDTH):{TITLE_WIDTH}}  {_cut(r.job.company, COMPANY_WIDTH)}"
        )
    if report.errors:
        lines += ["", "Errors:"] + [f"  {e}" for e in report.errors]
    return "\n".join(lines)


def job_detail(r: RankedJob) -> str:
    j = r.job
    out = [
        f"## {j.title} at {j.company}",
        "",
        f"- Key: `{j.short_key}` · via {j.via or 'unknown'} · {j.posted_at or 'date unknown'}",
        f"- Location: {j.location or 'not stated'} · Remote: {'yes' if j.work_from_home else 'not stated'}",
        f"- Salary: {j.salary or 'not stated'}",
    ]
    out += [f"- Apply: {link}" for link in j.apply_links[:2]]
    a = r.analysis
    if a is None:
        out += ["", f"BM25 score {r.score:.2f}. No Claude analysis yet."]
        return "\n".join(out)
    out += ["", f"**Fit {a.fit_score}/100 ({a.verdict}).** {a.summary}", "", "Matches:"]
    out += [f"- {m.requirement} (resume chunk {m.evidence_chunk})" for m in a.matches] or ["- none"]
    out += ["", "Gaps:"] + ([f"- {g}" for g in a.gaps] or ["- none"])
    if a.red_flags:
        out += ["", "Red flags:"] + [f"- {f}" for f in a.red_flags]
    return "\n".join(out)


def markdown(report: RunReport, day: date) -> str:
    parts = [f"# Job matches for {day.isoformat()}", "", "```", table(report), "```"]
    parts += ["", *(job_detail(r) + "\n" for r in report.results)]
    return "\n".join(parts)
