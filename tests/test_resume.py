import pytest

from jobmatch.resume import ResumeError, chunk_resume, load_resume_text


def test_load_txt_resume(tmp_path):
    path = tmp_path / "cv.txt"
    path.write_text("Hello resume")

    assert load_resume_text(path) == "Hello resume"


def test_missing_and_unsupported_files_raise(tmp_path):
    with pytest.raises(ResumeError, match="not found"):
        load_resume_text(tmp_path / "nope.pdf")

    docx = tmp_path / "cv.docx"
    docx.write_text("x")
    with pytest.raises(ResumeError, match="Unsupported"):
        load_resume_text(docx)


def test_empty_resume_raises(tmp_path):
    path = tmp_path / "cv.md"
    path.write_text("   \n")

    with pytest.raises(ResumeError, match="empty"):
        load_resume_text(path)


def test_chunk_resume_splits_on_blocks_and_bullets(resume_text):
    chunks = chunk_resume(resume_text)

    assert any("WooCommerce" in c for c in chunks)
    assert any("DNS, SSL" in c for c in chunks)
    assert all(c.strip() == c and c for c in chunks)


def test_chunk_resume_splits_inline_pdf_bullets():
    text = "Support lead at HostCo answering tickets daily •Wrote thirty help center articles for customers •Cut first reply time by half"

    chunks = chunk_resume(text)

    assert len(chunks) == 3
    assert chunks[1] == "Wrote thirty help center articles for customers"


def test_chunk_resume_redacts_email_and_phone():
    text = "Jane Tester +44 20 7946 0958 | jane.t+cv@example.com | Leeds, UK (UTC+0) remote"

    chunk = chunk_resume(text)[0]

    assert "example.com" not in chunk and "7946" not in chunk
    assert "[email]" in chunk and "[phone]" in chunk
    assert "Leeds, UK (UTC+0)" in chunk  # location stays: it matters for remote rules


def test_chunk_resume_merges_tiny_lines_and_caps_size():
    text = "A\nB\nC\n\n" + " ".join(["word"] * 300)

    chunks = chunk_resume(text, max_words=100)

    assert chunks[0].startswith("A B C word")  # the tiny piece joins the next one
    assert all(len(c.split()) <= 100 for c in chunks)
    assert sum(len(c.split()) for c in chunks) == 303  # no words lost
