"""OCR extraction service for finance documents."""
import re
from pathlib import Path


def _extract_dates(text: str) -> list[tuple[int, int]]:
    """Extract (year, month) tuples from text using common date patterns."""
    results: list[tuple[int, int]] = []

    # dd/mm/yyyy or dd-mm-yyyy or dd.mm.yyyy
    for m in re.finditer(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 2000 <= year <= 2099:
            results.append((year, month))
        elif 1 <= day <= 12 and 2000 <= year <= 2099:
            # Ambiguous: could be mm/dd/yyyy
            results.append((year, day))

    # yyyy-mm-dd (ISO format)
    for m in re.finditer(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", text):
        year, month = int(m.group(1)), int(m.group(2))
        if 2000 <= year <= 2099 and 1 <= month <= 12:
            results.append((year, month))

    return results


def _extract_amounts(text: str) -> list[float]:
    """Extract monetary amounts from text."""
    amounts: list[float] = []

    # Match patterns like 42.50, 1,234.56, 42,50 (European), EUR 42.50, $42.50
    for m in re.finditer(
        r"(?:EUR|USD|\$|TOTAL|AMOUNT|IMPORTE|SUMA)[:\s]*"
        r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})",
        text,
        re.IGNORECASE,
    ):
        raw = m.group(1)
        amounts.append(_parse_number(raw))

    # Standalone amounts on lines (larger numbers near bottom of receipt)
    for m in re.finditer(r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})", text):
        raw = m.group(1)
        val = _parse_number(raw)
        if val > 0:
            amounts.append(val)

    return amounts


def _parse_number(raw: str) -> float:
    """Parse a number string that may use European or US formatting."""
    # Check if using European format (comma as decimal separator)
    # Heuristic: if last separator is comma and followed by exactly 2 digits
    if re.match(r"^\d{1,3}(\.\d{3})*,\d{2}$", raw):
        # European: 1.234,56 -> 1234.56
        return float(raw.replace(".", "").replace(",", "."))
    else:
        # US/standard: 1,234.56 -> 1234.56
        return float(raw.replace(",", ""))


def extract_from_image(image_path: Path) -> dict:
    """Run OCR on an image and extract financial data.

    Returns dict with: raw_text, suggested_amount, suggested_year, suggested_month
    """
    import pytesseract
    from PIL import Image

    img = Image.open(image_path)
    raw_text = pytesseract.image_to_string(img, lang="spa+eng")

    return _parse_ocr_text(raw_text)


def extract_from_pdf(pdf_path: Path) -> dict:
    """Extract text from PDF and parse financial data.

    Tries text extraction first (pypdf). If no text found,
    converts first page to image and runs OCR.

    Returns dict with: raw_text, suggested_amount, suggested_year, suggested_month
    """
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)

    raw_text = "\n".join(text_parts).strip()

    if raw_text:
        return _parse_ocr_text(raw_text)

    # No text extracted - try OCR on first page
    try:
        import pytesseract
        from PIL import Image

        # Convert first page to image using pdf2image or pypdf rendering
        # Fall back to importing pdf2image if available
        from pdf2image import convert_from_path

        images = convert_from_path(str(pdf_path), first_page=1, last_page=1)
        if images:
            raw_text = pytesseract.image_to_string(images[0], lang="spa+eng")
            return _parse_ocr_text(raw_text)
    except ImportError:
        pass

    return _parse_ocr_text("")


def _parse_ocr_text(raw_text: str) -> dict:
    """Parse OCR text to extract financial data."""
    suggested_amount = None
    suggested_year = None
    suggested_month = None

    if raw_text:
        amounts = _extract_amounts(raw_text)
        if amounts:
            # Use the largest amount as the likely total
            suggested_amount = max(amounts)

        dates = _extract_dates(raw_text)
        if dates:
            # Use the first date found
            suggested_year, suggested_month = dates[0]

    return {
        "raw_text": raw_text,
        "suggested_amount": suggested_amount,
        "suggested_year": suggested_year,
        "suggested_month": suggested_month,
    }
