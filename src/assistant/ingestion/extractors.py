"""
Document extractors for text, PDF, and DOCX per PLAN.md section 8.

Extraction produces deterministic output.
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from docx import Document as DocxDocument


@dataclass
class ExtractionResult:
    """Result of text extraction."""
    text: str
    input_hash: str  # sha256(extracted_text)
    input_kind: str  # "text" | "pdf" | "docx"
    input_name: str | None  # filename or label


def _compute_hash(text: str) -> str:
    """Compute sha256 of extracted text per PLAN.md section 8.2."""
    return hashlib.sha256(text.encode()).hexdigest()


def extract_text(raw_text: str, label: str | None = None) -> ExtractionResult:
    """
    Extract from free text (pasted).

    Args:
        raw_text: Raw text input
        label: Optional label

    Returns:
        ExtractionResult
    """
    text = raw_text.strip()
    if not text:
        raise ValueError("Input text is empty")

    return ExtractionResult(
        text=text,
        input_hash=_compute_hash(text),
        input_kind="text",
        input_name=label,
    )


def extract_pdf(file_path: Path) -> ExtractionResult:
    """
    Extract text from PDF per PLAN.md section 8.1.

    Args:
        file_path: Path to PDF file

    Returns:
        ExtractionResult
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            pages.append(page_text)

    text = "\n\n".join(pages).strip()
    if not text:
        raise ValueError(f"No text extracted from PDF: {file_path.name}")

    return ExtractionResult(
        text=text,
        input_hash=_compute_hash(text),
        input_kind="pdf",
        input_name=file_path.name,
    )


def extract_docx(file_path: Path) -> ExtractionResult:
    """
    Extract text from DOCX per PLAN.md section 8.1.

    Args:
        file_path: Path to DOCX file

    Returns:
        ExtractionResult
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"DOCX file not found: {file_path}")

    doc = DocxDocument(str(file_path))
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)

    text = "\n\n".join(paragraphs).strip()
    if not text:
        raise ValueError(f"No text extracted from DOCX: {file_path.name}")

    return ExtractionResult(
        text=text,
        input_hash=_compute_hash(text),
        input_kind="docx",
        input_name=file_path.name,
    )
