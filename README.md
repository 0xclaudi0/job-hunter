# job-hunter

This tool finds remote jobs with the SerpApi Google Jobs API. It ranks the jobs against your resume and uses Claude to explain each match. Each claim in the explanation cites a part of your resume. The tool can also write a cover letter draft for a job.

## How it works

```
config.toml queries
      │
      ▼
SerpApi Google Jobs ──► SQLite cache (a repeated search inside 20 h costs no credits)
      │  follows next_page_token
      ▼
normalize + dedupe      same title + company on LinkedIn and Indeed → one job
      │
      ▼
filter                  title words you exclude, jobs you rejected or applied to
      │
      ▼
BM25 rank (resume = query, jobs = corpus) → top N
      │
      ▼
for each top job:
  retrieve evidence     BM25 again (job = query, resume chunks = corpus) → best 4 chunks
  Claude analysis       structured JSON: fit score, requirements, matches with chunk
                        numbers, gaps, red flags (for example "US residents only")
      │
      ▼
terminal table + output/matches-YYYY-MM-DD.md
```

The analysis is a small RAG step. Claude does not see your full resume. It sees only the chunks that the retrieval step picks for that job. Each match must cite one of those chunk numbers, and the code removes any citation to a chunk that Claude did not get. A claim with no evidence goes into the list of gaps.

### Design choices

- **BM25, not embeddings.** Job posts and resumes share exact terms such as "WooCommerce", "DNS" and "Zendesk", so keyword retrieval works well here. BM25 also needs no model download and runs in pure Python.
- **Claude reads only the top N jobs.** BM25 removes the clear misses for free. Claude gets only the jobs that remain, and the tool stores each analysis, so a job never goes to Claude twice.
- **Structured outputs.** The analysis uses a JSON schema (`output_config.format`), and Pydantic checks the reply. A reply that is not valid causes a clear error for that job only. The run continues with the other jobs.
- **Refusal fallback.** Requests use `fallbacks: "default"`. If a safety check declines a request, the API runs it again on a fallback model.
- **Privacy.** The tool removes emails and phone numbers from resume chunks before it sends them to Claude. The SerpApi cache key never contains your API key.
- **Untrusted input.** Job posts come from the web. The prompts put each post in a `<job_post>` block and tell Claude to ignore instructions inside it.

## Set up

You need Python 3.11 or newer.

```bash
python3.11 -m venv .venv
```

```bash
.venv/bin/pip install -e ".[dev]"
```

```bash
cp .env.example .env
```

```bash
cp config.example.toml config.toml
```

Put `SERPAPI_API_KEY` and `ANTHROPIC_API_KEY` in `.env`. Then edit `config.toml`: set `resume_path`, your queries, and the candidate notes. Claude treats the candidate notes as facts, for example where you can legally work.

## Use it

Search, rank and analyze:

```bash
.venv/bin/jobmatch run
```

Rank only, with no Claude calls. This costs SerpApi credits only:

```bash
.venv/bin/jobmatch run --no-llm
```

Show one job. Use the `KEY` column from the table:

```bash
.venv/bin/jobmatch show 3f9a2c1d
```

Write a cover letter draft. The tool saves it in `output/letters/`:

```bash
.venv/bin/jobmatch letter 3f9a2c1d
```

Record what you did with a job. The tool hides `rejected` and `applied` jobs in later runs:

```bash
.venv/bin/jobmatch mark 3f9a2c1d applied
```

## Cost

- **SerpApi:** One search for each query and each page. With 5 queries and `max_pages = 1`, a daily run uses about 150 searches each month. A second run on the same day uses the cache.
- **Claude:** One request for each new job in the top N. Jobs that already have an analysis cost nothing.

## Tests

```bash
.venv/bin/pytest --cov --cov-report=term-missing
```

The tests use saved SerpApi responses and a fake Claude client, so they make no network calls and cost nothing.

## Next steps

- Use the jobs that you mark `rejected` to lower the scores of similar jobs.
- Send a daily digest by email, or post it to a Slack channel.
- Add an evaluation set: 20 jobs with fit scores that you assign by hand, so that you can measure each prompt change.
