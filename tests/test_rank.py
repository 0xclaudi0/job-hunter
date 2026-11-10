from jobmatch.normalize import jobs_from_page
from jobmatch.rank import BM25, rank_jobs, retrieve_evidence, tokenize


def test_tokenize_keeps_tech_terms_and_drops_stopwords():
    tokens = tokenize("The C++ and Next.js developer, with PHP!")

    assert "c++" in tokens
    assert "next.js" in tokens
    assert "php" in tokens
    assert "the" not in tokens
    assert "and" not in tokens


def test_bm25_scores_relevant_document_higher():
    docs = [tokenize("wordpress php themes plugins"), tokenize("nursing patient care hospital")]
    bm25 = BM25(docs)

    scores = bm25.scores(tokenize("wordpress plugins"))

    assert scores[0] > scores[1]
    assert scores[1] == 0


def test_bm25_handles_empty_corpus():
    assert BM25([]).scores(["x"]) == []


def test_rank_jobs_puts_wordpress_job_above_nurse_job(page1, resume_text):
    jobs = jobs_from_page(page1, query="q")

    ranked = rank_jobs(resume_text, jobs)

    titles = [r.job.title for r in ranked]
    assert titles.index("WordPress Developer") < titles.index("Registered Nurse")
    assert ranked[0].score == 1.0  # scores are scaled to the best job
    assert all(0 <= r.score <= 1 for r in ranked)


def test_retrieve_evidence_returns_most_relevant_chunks():
    chunks = (
        "Answered support tickets about DNS and SSL.",
        "Built WordPress and WooCommerce sites.",
        "Enjoys hiking.",
    )

    evidence = retrieve_evidence(chunks, "WordPress WooCommerce developer", k=2)

    assert evidence[0] == (1, chunks[1])
    assert len(evidence) <= 2
    assert all(idx != 2 for idx, _ in evidence)  # zero-score chunks are left out
