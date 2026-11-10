"""Load a resume and split it into chunks for retrieval."""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT_CHUNK_WORDS = 80
_MIN_CHUNK_WORDS = 6
_BULLET = re.compile(r"^\s*(?:[-*•▪◦]|\d+[.)])\s+")
_INLINE_BULLET = re.compile(r"\s*[•▪◦]\s*")  # PDF text often puts bullets mid-line
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


class ResumeError(RuntimeError):
    pass


def load_resume_text(path: Path) -> str:
    path = Path(path).expanduser()
    if not path.exists():
        raise ResumeError(f"Resume not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _pdf_text(path)
    elif suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8")
    else:
        raise ResumeError(f"Unsupported resume type {suffix!r}. Use .pdf, .txt or .md")

    if not text.strip():
        raise ResumeError(f"Resume is empty or has no text layer: {path}")
    return text


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader  # imported here so text resumes need no PDF library

    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as err:  # pypdf raises many error types for damaged files
        raise ResumeError(f"Could not read PDF {path}: {err}") from err


def _split_long(words: list[str], max_words: int) -> list[str]:
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def redact_contact_details(text: str) -> str:
    """Chunks go to the Claude API. Emails and phone numbers do not help a match, so drop them."""
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text))


def chunk_resume(text: str, max_words: int = DEFAULT_CHUNK_WORDS) -> tuple[str, ...]:
    """One chunk per bullet or paragraph. Tiny lines merge into the next; long ones split."""
    text = _INLINE_BULLET.sub("\n- ", redact_contact_details(text))
    pieces: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        current: list[str] = []
        for line in block.splitlines():
            if _BULLET.match(line) and current:
                pieces.append(" ".join(current))
                current = []
            current.append(_BULLET.sub("", line).strip())
        if current:
            pieces.append(" ".join(current))

    chunks: list[str] = []
    pending = ""
    for piece in (" ".join(p.split()) for p in pieces):
        if not piece:
            continue
        merged = f"{pending} {piece}".strip() if pending else piece
        if len(merged.split()) < _MIN_CHUNK_WORDS:
            pending = merged
            continue
        chunks.extend(_split_long(merged.split(), max_words))
        pending = ""
    if pending:
        chunks.append(pending)
    return tuple(chunks)
