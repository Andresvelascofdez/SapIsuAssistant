"""CV file storage and text extraction utilities."""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _safe_filename(name: str) -> str:
    base = Path(name).name.strip() or "cv"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return safe or "cv"


def copy_cv_file(source_path: Path | str, data_root: Path | str = Path("data")) -> Path:
    source = Path(source_path)
    recruitment_dir = Path(data_root) / "recruitment"
    cvs_dir = recruitment_dir / "cvs"
    cvs_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(source.name)
    destination = cvs_dir / f"{uuid.uuid4().hex}_{safe}"
    shutil.copy2(source, destination)
    return destination


def extract_text_from_file(file_path: Path | str) -> tuple[str, str | None]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".txt":
            return _extract_txt(path), None
        if suffix == ".pdf":
            return _extract_pdf(path), None
        if suffix == ".docx":
            return _extract_docx(path), None
        return "", f"Unsupported CV file type: {suffix or 'unknown'}."
    except Exception as exc:
        return "", f"CV file was stored, but text extraction failed: {exc}"


def import_cv(source_path: Path | str, data_root: Path | str = Path("data")) -> dict[str, Any]:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(source)
    copied = copy_cv_file(source, data_root=data_root)
    text, error = extract_text_from_file(copied)
    return {
        "cv_file_path": str(copied),
        "cv_text": text,
        "error": error,
    }


def _extract_txt(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="ignore")


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(part.strip() for part in parts if part.strip())


def _extract_docx(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
