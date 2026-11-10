from jobmatch.normalize import dedupe_key, job_from_serpapi, jobs_from_page


def test_job_from_serpapi_maps_fields(page1):
    job = job_from_serpapi(page1["jobs_results"][0], query="WordPress developer")

    assert job.title == "WordPress Developer"
    assert job.company == "Acme Web Studio Inc."
    assert job.via == "LinkedIn"
    assert job.work_from_home is True
    assert job.posted_at == "2 days ago"
    assert job.apply_links == ("https://example.com/apply/acme",)
    assert "WooCommerce" in job.description
    assert "Good written English" in job.description  # highlights are folded in
    assert job.query == "WordPress developer"


def test_job_without_title_is_skipped(page1):
    assert job_from_serpapi(page1["jobs_results"][3], query="q") is None


def test_dedupe_key_ignores_case_and_punctuation():
    a = dedupe_key("WordPress Developer", "Acme Web Studio Inc.")
    b = dedupe_key("wordpress developer", "Acme Web Studio Inc")
    c = dedupe_key("WordPress Developer", "Other Co")

    assert a == b
    assert a != c


def test_jobs_from_page_drops_broken_records(page1):
    jobs = jobs_from_page(page1, query="q")

    assert [j.company for j in jobs] == ["Acme Web Studio Inc.", "City Hospital", "SaaSCo"]


def test_jobs_from_page_handles_missing_results():
    assert jobs_from_page({}, query="q") == []
