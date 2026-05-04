"""OCR extraction service for finance documents."""
import io
import logging
import re
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# Month name mappings for text-based date extraction
_MONTH_NAMES_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_NAMES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "ene": 1, "feb": 2, "mar": 3, "abr": 4,
    "jun": 6, "jul": 7, "ago": 8, "sep": 9,
    "oct": 10, "nov": 11, "dic": 12,
}
_ALL_MONTH_NAMES = {**_MONTH_NAMES_EN, **_MONTH_NAMES_ES}

# Tesseract path on Windows
_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _configure_tesseract():
    """Set Tesseract binary path if available on Windows."""
    if Path(_TESSERACT_PATH).exists():
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH


def _resolve_year(y: int) -> int:
    """Resolve 2-digit years to 4-digit (00-99 -> 2000-2099)."""
    if 0 <= y <= 99:
        return 2000 + y
    return y


def _extract_dates(text: str) -> list[tuple[int, int, int]]:
    """Extract (year, month, day) tuples from text using common date patterns.

    Supports: dd/mm/yyyy, dd/mm/yy, dd.mm.yyyy, dd-mm-yyyy,
    yyyy-mm-dd, "Month dd, yyyy", "dd Month yyyy", "Month yyyy".
    Also handles garbled OCR dates like "3101/28" (DD merged with MM).
    Dates followed by a timestamp (HH:MM) are prioritized.
    """
    # Clean version/terminal strings that produce fake dates
    cleaned = _clean_ocr_noise(text)

    results: list[tuple[int, int, int]] = []
    timestamped: list[tuple[int, int, int]] = []
    seen = set()

    def _add(year: int, month: int, day: int = 1, *, has_time: bool = False):
        year = _resolve_year(year)
        if 2000 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31:
            key = (year, month)
            if key not in seen:
                seen.add(key)
                entry = (year, month, max(day, 1))
                if has_time:
                    timestamped.append(entry)
                else:
                    results.append(entry)

    # ── Pass 1: Date+time patterns (highest priority for POS receipts) ──
    # DD/MM/YYYY HH:MM or DD/MM/YY HH:MM:SS
    for m in re.finditer(
        r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\s+\d{2}:\d{2}",
        cleaned,
    ):
        g1, g2, g3 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if g3 >= 100:  # 4-digit year: dd/mm/yyyy
            if 1 <= g2 <= 12:
                _add(g3, g2, g1, has_time=True)
        else:  # 2-digit year: dd/mm/yy
            if 1 <= g2 <= 12:
                _add(_resolve_year(g3), g2, g1, has_time=True)

    # DDMM/YY HH:MM — OCR sometimes drops separator between DD and MM
    # e.g., "3101/28 15:21:32" for "31/01/26 15:21:32"
    for m in re.finditer(
        r"(\d{2})(\d{2})/(\d{2})\s+\d{2}:\d{2}",
        cleaned,
    ):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            _add(_resolve_year(year), month, day, has_time=True)

    # ── Pass 2: Standard date patterns (no timestamp required) ──

    # yyyy-mm-dd (ISO format) - check first to prioritize 4-digit years
    for m in re.finditer(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", cleaned):
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _add(year, month, day)

    # dd/mm/yyyy or dd-mm-yyyy or dd.mm.yyyy (4-digit year)
    for m in re.finditer(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", cleaned):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12:
            _add(year, month, day)
        elif 1 <= day <= 12:
            _add(year, day, month)

    # dd/mm/yy (2-digit year) - must not be part of a longer numeric/version sequence
    for m in re.finditer(r"(?<![.\d])(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})(?!\d)", cleaned):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12:
            _add(_resolve_year(year), month, day)
        elif 1 <= day <= 12:
            _add(_resolve_year(year), day, month)

    # Text month patterns: "Feb 2, 2026", "February 2, 2026", "2 Feb 2026"
    month_pattern = "|".join(re.escape(k) for k in _ALL_MONTH_NAMES.keys())

    # "Month dd, yyyy" or "Month dd yyyy"
    for m in re.finditer(
        rf"({month_pattern})\s+(\d{{1,2}}),?\s+(\d{{4}}|\d{{2}})\b",
        cleaned,
        re.IGNORECASE,
    ):
        month_name = m.group(1).lower()
        day = int(m.group(2))
        year = int(m.group(3))
        if month_name in _ALL_MONTH_NAMES:
            _add(year, _ALL_MONTH_NAMES[month_name], day)

    # "dd Month yyyy"
    for m in re.finditer(
        rf"(\d{{1,2}})\s+({month_pattern})\s+(\d{{4}}|\d{{2}})\b",
        cleaned,
        re.IGNORECASE,
    ):
        day = int(m.group(1))
        month_name = m.group(2).lower()
        year = int(m.group(3))
        if month_name in _ALL_MONTH_NAMES:
            _add(year, _ALL_MONTH_NAMES[month_name], day)

    # "Month yyyy" (no day)
    for m in re.finditer(
        rf"({month_pattern})\s+(\d{{4}})\b",
        cleaned,
        re.IGNORECASE,
    ):
        month_name = m.group(1).lower()
        year = int(m.group(2))
        if month_name in _ALL_MONTH_NAMES:
            _add(year, _ALL_MONTH_NAMES[month_name])

    # Timestamped dates get priority (prepend to results)
    return timestamped + results


def _clean_ocr_noise(text: str) -> str:
    """Remove version strings, terminal IDs and AID numbers that produce fake amounts/dates."""
    cleaned = re.sub(r'[Vv]\d{2}\.\d{2}-\d{4}-\w', '', text)  # V01.59-0000-L
    cleaned = re.sub(r'\d{7,}[.\-]\d+[.\-]\d+[.\-]\d+', '', cleaned)  # 0002503.14.9.47
    cleaned = re.sub(r'A\d{13,}', '', cleaned)  # AID: A0000000041010
    return cleaned


# Common OCR character-to-digit substitutions for garbled receipt text
# NOTE: S is handled separately (ambiguous — could be 3 or 5)
_OCR_DIGIT_FIXES = [
    ('O', '0'), ('B', '8'), (']', '1'), ('[', '1'),
    ('|', '1'), ('!', '1'), ('l', '1'), ('{', '1'), ('}', '1'),
]

# Extended fixes used ONLY after currency prefix is stripped (safe context)
_OCR_DIGIT_FIXES_EXTENDED = _OCR_DIGIT_FIXES + [
    ('U', '0'),  # 0 often looks like U in poor OCR
]


def _extract_amounts(text: str) -> list[float]:
    """Extract monetary amounts from text using a priority system.

    Priority 1: TOTAL/AMOUNT keywords (most reliable total indicators)
    Priority 1b: Subtotal + VAT computation (fallback for garbled TOTAL lines)
    Priority 1c: OCR error-corrected keyword lines (last keyword resort)
    Priority 2: Currency-adjacent amounts (EUR, €, $)
    Priority 3: Standalone decimal numbers (least reliable)

    Returns amounts from the highest priority level that has matches.
    The caller should use max() to pick the suggested total.
    """
    _NUM = r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})"

    # ── Preprocess: remove version/terminal strings with fake decimals ──
    cleaned = _clean_ocr_noise(text)

    # ── Priority 1: TOTAL / AMOUNT keywords ──
    # TOTAL-EFT must precede TOTAL in alternation.
    # (?<!SUB) prevents matching "subtotal" as "TOTAL".
    total_amounts: list[float] = []

    def _line_has_cash(match) -> bool:
        """Check if the line containing a match also has CASH/ΜΕΤΡΗΤΑ/CHANGE."""
        ls = cleaned.rfind('\n', 0, match.start()) + 1
        le = cleaned.find('\n', match.end())
        if le == -1:
            le = len(cleaned)
        return bool(re.search(
            r'ΜΕΤΡΗΤΑ|METP.TA|CASH|CASK|CHANGE',
            cleaned[ls:le], re.IGNORECASE,
        ))

    for m in re.finditer(
        r"(?:TOTAL[- ]?EFT|(?<!SUB)TOTAL|AMOUNT|IMPORTE|SUMA|SALE|PURCHASE)"
        r"[:\s]*(?:EUR|€|USD|\$)?[:\s]*" + _NUM,
        cleaned,
        re.IGNORECASE,
    ):
        if not _line_has_cash(m):
            total_amounts.append(_parse_number(m.group(1)))

    # Greek receipt totals — expanded OCR variants of ΣΥΝΟΛΟ
    # Covers: ΣYNOAO, —YNOAO, EYNOAD, SYNOLO, EYNOND, EINOND, E1NOND, etc.
    for m in re.finditer(
        r"(?:ΣΥΝΟΛΟ|SYNOL[OΟ]"
        r"|[ΣΕE\u2014\-]YNOA[OΟDP]"
        r"|EYNOAO|\u2014YNOAO"
        r"|EYNOND|E[I1]NOND)"
        r"[^\d\n]{0,5}" + _NUM,
        cleaned,
        re.IGNORECASE,
    ):
        if not _line_has_cash(m):
            total_amounts.append(_parse_number(m.group(1)))

    if total_amounts:
        return total_amounts

    # ── Priority 1b: Subtotal + VAT computation ──
    # When TOTAL line is garbled beyond recognition but subtotal and VAT are clear
    subtotal_amounts: list[float] = []
    for m in re.finditer(
        r"SUBTOTAL[:\s]*(?:EUR|€|USD|\$)?[:\s]*" + _NUM,
        cleaned,
        re.IGNORECASE,
    ):
        subtotal_amounts.append(_parse_number(m.group(1)))
    if subtotal_amounts:
        vat_val = _extract_vat(cleaned)
        if vat_val is not None:
            total_amounts.append(round(max(subtotal_amounts) + vat_val, 2))
            return total_amounts

    # ── Priority 1c: OCR error-corrected keyword lines ──
    # For garbled amounts like "AMOUNT EURS9, 70" or "AMOUNT EURSU U0"
    for m in re.finditer(
        r"(?:TOTAL[- ]?EFT|(?<!SUB)TOTAL|AMOUNT|SALE|PURCHASE)"
        r"[:\s]+(.{3,25})",
        cleaned,
        re.IGNORECASE,
    ):
        raw_after = m.group(1)

        # Step 1: Strip currency prefix (including garbled variants like FUR, EMR, CUR)
        raw_stripped = raw_after.strip()
        after_currency = re.sub(
            r'^(?:EUR|FUR|EOR|CUR|EMR|EER|BUR|\u20ac|USD|\$)\s*',
            '', raw_stripped, flags=re.IGNORECASE,
        )
        currency_found = (after_currency != raw_stripped)
        if not after_currency.strip():
            after_currency = raw_stripped

        # Step 2: Handle S ambiguity (could be 3 or 5 in OCR)
        has_s = 'S' in after_currency
        s_variants = ['3', '5'] if has_s else [None]
        s_candidates: list[float] = []
        for s_val in s_variants:
            corrected = after_currency
            if s_val is not None:
                corrected = corrected.replace('S', s_val)
            # Apply extended OCR digit corrections (safe after currency strip)
            for old, new in _OCR_DIGIT_FIXES_EXTENDED:
                corrected = corrected.replace(old, new)
            # Remove remaining letter characters
            corrected = re.sub(r'[A-Za-z€$]+', '', corrected).strip()

            # Try 1: collapse whitespace (e.g. "39, 70" → "39,70")
            collapsed = re.sub(r'\s+', '', corrected)
            num_m = re.match(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', collapsed)
            if num_m:
                s_candidates.append(_parse_number(num_m.group(1)))
                continue

            # Try 2: treat spaces as potential decimal points (e.g. "50 00" → "50.00")
            dotted = re.sub(r'\s+', '.', corrected).lstrip('.')
            num_m = re.match(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', dotted)
            if num_m:
                s_candidates.append(_parse_number(num_m.group(1)))

        if s_candidates and currency_found:
            if has_s and len(s_candidates) == 2:
                # Smart S resolution based on garble level of the text
                digit_chars = sum(1 for c in after_currency if c.isdigit())
                alnum_chars = sum(1 for c in after_currency if c.isalnum())
                garble_ratio = 1 - (digit_chars / max(alnum_chars, 1))
                if garble_ratio > 0.5:
                    # Heavily garbled: S→5 is most common visual confusion
                    total_amounts.append(max(s_candidates))
                else:
                    # Mostly clear digits: be conservative
                    total_amounts.append(min(s_candidates))
            else:
                total_amounts.extend(s_candidates)

    if total_amounts:
        return total_amounts

    # ── Priority 1d: Tip computation ──
    # POS receipts with "(subtotal + tip)" pattern, e.g. "(122.50 + 12.26"
    tip_amounts: list[float] = []
    for m in re.finditer(
        r'\(?' + _NUM + r'\s*\+\s*' + _NUM,
        cleaned,
    ):
        val = _parse_number(m.group(1)) + _parse_number(m.group(2))
        tip_amounts.append(round(val, 2))
    if tip_amounts:
        return tip_amounts

    # ── Priority 2: Currency-adjacent amounts ──
    currency_amounts: list[float] = []

    # "EUR 42.50", "€42.50", "$1,234.56", "EUR40.00"
    for m in re.finditer(
        r"(?:EUR|USD|\$|€)\s*" + _NUM,
        cleaned,
        re.IGNORECASE,
    ):
        currency_amounts.append(_parse_number(m.group(1)))

    # "42.50 EUR", "1,234.56€"
    for m in re.finditer(
        _NUM + r"\s*(?:EUR|€|USD|\$)",
        cleaned,
        re.IGNORECASE,
    ):
        currency_amounts.append(_parse_number(m.group(1)))

    if currency_amounts:
        return currency_amounts

    # ── Priority 3: Standalone decimal numbers ──
    standalone: list[float] = []
    for m in re.finditer(_NUM, cleaned):
        val = _parse_number(m.group(1))
        if val > 0:
            standalone.append(val)

    return standalone


def _parse_number(raw: str) -> float:
    """Parse a number string that may use European or US formatting."""
    # Check if using European format (comma as decimal separator)
    # Heuristic: if last separator is comma and followed by exactly 2 digits
    if re.match(r"^\d{1,3}(\.\d{3})*,\d{2}$", raw):
        # European: 1.234,56 -> 1234.56
        return float(raw.replace(".", "").replace(",", "."))
    else:
        # US/standard: 1,234.56 -> 1234.56
        try:
            return float(raw.replace(",", ""))
        except ValueError:
            # Handle ambiguous multi-dot: "1.043.50" → treat last dot as decimal
            parts = raw.replace(",", "").split(".")
            if len(parts) >= 3 and len(parts[-1]) == 2:
                return float("".join(parts[:-1]) + "." + parts[-1])
            return 0.0


def _extract_client_name(text: str) -> str | None:
    """Extract client/recipient name from invoice text.

    Looks for patterns like 'Cobrar a:', 'Invoice To:', 'Bill To:', etc.
    Returns the name on the same line or the next non-empty line.
    """
    patterns = [
        r"(?:Cobrar\s+a|Facturar\s+a|Cliente)\s*:\s*(.+)",
        r"(?:Invoice\s+To|Bill\s+To|Client|Customer)\s*:\s*(.+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # Clean: take first line only, remove trailing punctuation
            name = name.split("\n")[0].strip().rstrip(".,;:")
            if len(name) >= 2:
                return name

    # Fallback: look for the line after "Cobrar a:" or "Invoice To:" headers
    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"(?:Cobrar\s+a|Invoice\s+To|Bill\s+To|Facturar\s+a)\s*:?\s*$", stripped, re.IGNORECASE):
            # The name is on the next non-empty line
            for j in range(i + 1, min(i + 3, len(lines))):
                candidate = lines[j].strip()
                if candidate and len(candidate) >= 2:
                    return candidate.rstrip(".,;:")

    return None


def _extract_invoice_number(text: str) -> str | None:
    """Extract invoice number from text.

    Looks for patterns like 'FACTURA #24', 'Invoice no.: 25', 'Invoice Number: INV-001'.
    """
    patterns = [
        r"FACTURA\s*[#nN°ºo.]*\s*:?\s*(\S+)",
        r"Invoice\s*(?:no|number|num|#|n[°ºo])[.\s:]*\s*(\S+)",
        r"Factura\s*(?:no|número|num|#|n[°ºo])[.\s:]*\s*(\S+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            num = m.group(1).strip().rstrip(".,;:")
            if num:
                return num
    return None


def _extract_vat(text: str) -> float | None:
    """Extract explicit VAT/IVA/ΦΠΑ amount from receipt or invoice text.

    Only returns when the VAT amount is explicitly stated.
    Returns the first match found, or None if no VAT line present.
    """
    _NUM = r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})"

    # "VAT: 5.00", "IVA (19%): 5.00 EUR", "ΦΠΑ 24%: 5.00", "VA] EUR 5.19"
    # Handles OCR garbles of "VAT" → "VA]", "VA|", "VA!", etc.
    for m in re.finditer(
        r"(?:VA[T\]\|!1l}]|IVA|ΦΠΑ)\s*(?:\(?\d+(?:[.,]\d+)?%\)?)?\s*[:\s]*(?:EUR|€|USD|\$)?\s*" + _NUM,
        text,
        re.IGNORECASE,
    ):
        return _parse_number(m.group(1))

    # Amount before currency: "VAT (19%): 210.00 EUR"
    for m in re.finditer(
        r"(?:VA[T\]\|!1l}]|IVA|ΦΠΑ)\s*(?:\(?\d+(?:[.,]\d+)?%\)?)?\s*[:\s]*" + _NUM + r"\s*(?:EUR|€|USD|\$)",
        text,
        re.IGNORECASE,
    ):
        return _parse_number(m.group(1))

    return None


# ── Merchant extraction ──

# Trailing company entity suffixes to strip (not business-type words like RESTAURANT)
_ENTITY_SUFFIXES_RE = re.compile(
    r'\s+(?:LTD|LLC|INC|CORP|S\.?L\.?|S\.?A\.?|GmbH|CO\.?|LIMITED|COMPANY)\s*$',
    re.IGNORECASE,
)

# OCR chars commonly confused with "I" — used for trailing-I merge
_OCR_I_CHARS = set('IJ|]l1!')


def _clean_merchant_name(name: str) -> str:
    """Strip OCR garbage prefixes/suffixes from merchant name."""
    cleaned = name
    for _ in range(5):  # iterate to handle mixed garbage like "_ fi | Fe NAME"
        prev = cleaned
        # Remove leading non-alphabetic characters (_, |, —, digits, punctuation)
        cleaned = re.sub(r"^[^a-zA-ZΑ-Ωα-ω]+", "", cleaned).strip()
        # Remove leading 1-2 char words (any case) that are likely OCR garbage
        cleaned = re.sub(r"^[a-zA-Z]{1,2}\s+", "", cleaned).strip()
        # Remove leading Title Case 1-3 char words (e.g. "Nei") but not ALL-CAPS
        cleaned = re.sub(r"^[A-Z][a-z]{0,2}\s+(?![A-Z][a-z])", "", cleaned).strip()
        # Remove leading lowercase 1-3 char words only before ALL-CAPS or abbreviation
        cleaned = re.sub(r"^[a-z]{1,3}\s+(?=[A-Z]{2,}|[A-Z]\.[A-Z])", "", cleaned).strip()
        if cleaned == prev:
            break
    # Strip trailing OCR garbage: pipes, brackets, etc.
    cleaned = re.sub(r"[\s|}\])]+$", "", cleaned).strip()
    # Trailing single char: check if it's a detached "I" (common OCR split)
    m_trail = re.match(r'^(.*\b[A-Z]{5,})\s+([IJl1|!\]])$', cleaned)
    if m_trail:
        # Merge detached OCR-I variant back as "I" (e.g., "AKROYIAL J" → "AKROYIALI")
        cleaned = m_trail.group(1) + 'I'
    else:
        # Remove other trailing single chars (typical OCR noise)
        cleaned = re.sub(r"\s+[A-Za-z]$", "", cleaned).strip()
    # Strip trailing company entity suffixes (LTD, LLC, etc.)
    cleaned = _ENTITY_SUFFIXES_RE.sub('', cleaned).strip()
    # Add space in abbreviations: "R.A.M.OIL" → "R.A.M. OIL"
    cleaned = re.sub(r"\.([A-Z]{2,})", r". \1", cleaned)
    return cleaned if len(cleaned) >= 3 else name


def _extract_merchant(text: str) -> str | None:
    """Extract merchant/business name from receipt text using scored candidates.

    Uses a scoring system to pick the best merchant name:
    - Company suffixes (RESTAURANT, LTD, etc.) get bonus points
    - Earlier lines get position bonus
    - Blacklisted tokens (payment processors) get heavy penalty
    - Address-like lines get penalty
    """
    # Common company suffixes that indicate a business name
    company_suffixes = re.compile(
        r"\b(?:LTD|LLC|INC|CORP|S\.?L\.?|S\.?A\.?|GmbH|"
        r"GMBH|CO\.?|COMPANY|LIMITED|RESTAURANT|BAR|CAFE|TAVERN[AE]?|"
        r"OIL|PETROL|PETROLENA|PETROLINA|STATION|KITI|PYLA|NOSH|"
        r"DROMOLAXIA|MOSFILOTI|COD)\b",
        re.IGNORECASE,
    )

    # Skip patterns - lines that are NEVER merchant names
    skip_patterns = re.compile(
        r"^(?:\d+[/\-.]|RECEIPT|RECIBO|TICKET|FACTURA|INVOICE|"
        r"TAX\b|VAT\b|IVA\b|TOTAL|SUBTOTAL|CHANGE|CASH|CARD|VISA|"
        r"MASTERCARD|DEBIT|CREDIT|DATE|FECHA|TIME|HORA|PURCHASE|"
        r"TEL|FAX|WWW\.|HTTP|@|SALE|AMOUNT|\*+|---+|===+|"
        r"JCC\b|PAYMENT|SYSTEMS|Member\s|Phone\b|Viva\b|Worldline\b|\s*$)",
        re.IGNORECASE,
    )

    # Blacklist tokens — penalize lines containing payment processor names etc.
    _BLACKLIST = {
        'JCC', 'VIVA', 'WORLDLINE', 'PAYMENT', 'PAYMENTS', 'SYSTEMS',
        'CARDHOLDER', 'COPY', 'AUTH', 'VERSION', 'VERSIONS',
        'MEMBER', 'PHONE', 'RECEIPT', 'APPROVED', 'CONTACTLESS',
        'VERIFIED', 'DEVICE',
    }

    # Address pattern: digits near street/road indicators
    _ADDRESS_RE = re.compile(
        r"\d+.*\b(?:STR|STREET|AVE|AVENUE|ROAD|RD|LEOFOROS|LEOF|"
        r"MAKARIOU|DEMOKRATIAS|PRODROMOU|NEROU)\b",
        re.IGNORECASE,
    )

    lines = text.strip().split("\n")
    candidates: list[tuple[int, int, str]] = []  # (score, line_index, text)

    for i, line in enumerate(lines[:20]):
        cleaned = line.strip()
        if not cleaned or len(cleaned) < 3:
            continue
        if skip_patterns.match(cleaned):
            continue
        # Skip purely numeric lines
        if re.match(r"^[\d\s.,/\-:]+$", cleaned):
            continue
        # Skip very short single-char garbage from OCR
        if len(cleaned.replace(" ", "")) < 3:
            continue

        score = 0

        # Position bonus: earlier lines are more likely merchant names (max 10)
        score += max(0, 10 - i)

        # Company suffix bonus
        if company_suffixes.search(cleaned):
            score += 20

        # Blacklist penalty: any blacklisted word on the line
        words = set(re.findall(r'[A-Za-z]+', cleaned.upper()))
        if words & _BLACKLIST:
            score -= 50

        # Address pattern penalty
        if _ADDRESS_RE.search(cleaned):
            score -= 15

        candidates.append((score, i, cleaned))

    if not candidates:
        return None

    # Pick highest score, break ties by earliest line
    candidates.sort(key=lambda x: (-x[0], x[1]))
    best = candidates[0][2]

    # Clean up: remove leading digits/punctuation and OCR garbage
    name = re.sub(r"^\d+[.\s]*", "", best).strip()
    name = _clean_merchant_name(name)
    return name if len(name) >= 3 else None


# ── OCR engine functions ──

def _run_tesseract(image, psm: int = 6) -> str:
    """Run pytesseract on a PIL Image, returning extracted text."""
    import pytesseract
    _configure_tesseract()
    return pytesseract.image_to_string(image, config=f"--psm {psm}")


def _alpha_count(text: str) -> int:
    """Count alphabetic characters in text."""
    return sum(1 for c in text if c.isalpha())


def _preprocess_image(image):
    """Enhance image contrast/threshold for better OCR on poor quality images."""
    from PIL import ImageEnhance, ImageOps

    gray = ImageOps.grayscale(image)
    enhanced = ImageEnhance.Contrast(gray).enhance(2.0)
    threshold = enhanced.point(lambda x: 0 if x < 140 else 255, '1')
    return threshold.convert('L')


def _preprocess_variants(image):
    """Generate multiple preprocessed image variants for OCR retry.

    Returns a list of PIL images with different contrast/threshold/filter
    combinations to maximize OCR success on poor-quality scans.
    """
    from PIL import ImageEnhance, ImageOps, ImageFilter

    variants = []
    gray = ImageOps.grayscale(image)

    # Variant 1: High contrast + fixed threshold (original method)
    v1 = ImageEnhance.Contrast(gray).enhance(2.0)
    v1 = v1.point(lambda x: 0 if x < 140 else 255, '1').convert('L')
    variants.append(v1)

    # Variant 2: Higher contrast + lower threshold (for faint text)
    v2 = ImageEnhance.Contrast(gray).enhance(3.0)
    v2 = v2.point(lambda x: 0 if x < 120 else 255, '1').convert('L')
    variants.append(v2)

    # Variant 3: Sharpened + medium threshold
    v3 = gray.filter(ImageFilter.SHARPEN)
    v3 = ImageEnhance.Contrast(v3).enhance(2.5)
    v3 = v3.point(lambda x: 0 if x < 130 else 255, '1').convert('L')
    variants.append(v3)

    # Variant 4: Inverted (for dark background receipts)
    v4 = ImageOps.invert(gray)
    v4 = ImageEnhance.Contrast(v4).enhance(2.0)
    v4 = v4.point(lambda x: 0 if x < 140 else 255, '1').convert('L')
    variants.append(v4)

    return variants


def _ocr_with_retry(image) -> str:
    """Run OCR with preprocessing retry when initial result is poor.

    Tries the raw image first, then multiple preprocessed variants with
    different page segmentation modes. Keeps the result with the most
    alphabetic characters (best OCR quality indicator).
    """
    raw_text = _run_tesseract(image)
    best_text = raw_text
    best_alpha = _alpha_count(raw_text)

    if best_alpha < 50:
        try:
            for variant in _preprocess_variants(image):
                for psm in [6, 4, 3]:
                    attempt = _run_tesseract(variant, psm=psm)
                    attempt_alpha = _alpha_count(attempt)
                    if attempt_alpha > best_alpha:
                        best_text = attempt
                        best_alpha = attempt_alpha
        except Exception as e:
            log.debug("Image preprocessing failed: %s", e)

    return best_text


def _generate_ocr_variants(image) -> list[str]:
    """Generate multiple OCR text variants from an image using various preprocessing.

    Produces texts from different scales, contrasts, thresholds, and PSM modes.
    Used to increase chances of extracting amounts and merchants from poor scans.
    """
    from PIL import ImageOps, ImageEnhance, ImageFilter, Image as PILImage

    texts: list[str] = []

    # Always try raw image first
    try:
        raw = _run_tesseract(image)
        if raw and raw.strip():
            texts.append(raw)
    except Exception:
        pass

    gray = ImageOps.grayscale(image)

    # Determine scales based on image size (large images benefit from downscaling)
    scales = [1.0]
    max_dim = max(image.size)
    if max_dim > 2500:
        scales.append(0.5)
    if max_dim > 3500:
        scales.append(0.4)

    # Focused set of contrast/threshold combos known to work well
    preprocess_configs = [
        (2.0, 140), (3.0, 120), (4.0, 120), (1.0, 180), (5.0, 180),
    ]

    try:
        for scale in scales:
            if scale != 1.0:
                w, h = int(gray.width * scale), int(gray.height * scale)
                base = gray.resize((w, h), PILImage.LANCZOS)
            else:
                base = gray

            for contrast, thresh in preprocess_configs:
                v = ImageEnhance.Contrast(base).enhance(contrast)
                v = v.point(lambda x: 0 if x < thresh else 255, '1').convert('L')
                for psm in [6, 3]:
                    t = _run_tesseract(v, psm=psm)
                    if t and t.strip():
                        texts.append(t)

            # Also try inverted with multiple settings
            inv = ImageOps.invert(base)
            for inv_c, inv_t, inv_psm in [(4.0, 120, 4), (5.0, 100, 4)]:
                vi = ImageEnhance.Contrast(inv).enhance(inv_c)
                vi = vi.point(lambda x: 0 if x < inv_t else 255, '1').convert('L')
                t = _run_tesseract(vi, psm=inv_psm)
                if t and t.strip():
                    texts.append(t)
    except Exception as e:
        log.debug("Multi-variant OCR failed: %s", e)

    return texts


def _is_garbage_merchant(name: str | None) -> bool:
    """Check if a merchant name is likely OCR garbage."""
    if not name:
        return True
    if len(name) < 4:
        return True
    alpha_ratio = sum(1 for c in name if c.isalpha()) / max(len(name), 1)
    if alpha_ratio < 0.5:
        return True
    # All lowercase strings are typically OCR noise
    if name.islower() and len(name) < 15:
        return True
    # Contains 3+ digit sequences (noise like "383")
    if re.search(r'\d{3,}', name):
        return True
    # Contains comma followed by digits (garbled text like ", 383")
    if re.search(r',\s*\d{2,}', name):
        return True
    # Contains special chars that don't belong in merchant names
    if re.search(r'[|*\[\]{}@#%^&+=?:]', name):
        return True
    # Non-ASCII currency symbols mixed in (like euro in middle of name)
    if re.search(r'[^\x00-\x7F]', name) and not re.match(r'^[^\x00-\x7F]', name):
        return True
    # Words starting with digit followed by uppercase letters (OCR garbage like "4OSO")
    if re.search(r'\b\d[A-Z]+\b', name):
        return True
    # Words with 3+ repeated same character (like "Resss")
    if re.search(r'(.)\1{2,}', name):
        return True
    # Mixed-case words that look garbled: 2+ uppercase then 2+ lowercase (like "HGResss")
    for word in name.split():
        if len(word) >= 5 and re.match(r'[A-Z]{2,}[a-z]{2,}', word):
            return True
    # Short hyphenated parts with inconsistent case — OCR artifact (like "boa-Vus")
    if re.search(r'\b[a-z]{2,5}-[A-Z]', name):
        return True
    # Name ends with comma or isolated period (OCR garbage)
    if re.search(r'[,.]$', name.strip()):
        return True
    # Words with 5+ chars and < 20% vowels — likely garbled consonant clusters
    _vowels = set('aeiouAEIOU')
    for word in re.findall(r'[A-Za-z]+', name):
        if len(word) >= 5:
            vowel_count = sum(1 for c in word if c in _vowels)
            if vowel_count / len(word) < 0.2:
                return True
    # Too many short words (4+ words and >50% are 1-2 chars) — OCR noise
    words = name.split()
    if len(words) >= 4:
        short_words = sum(1 for w in words if len(w) <= 2)
        if short_words / len(words) > 0.5:
            return True
    return False


def _score_merchant(name: str | None) -> int:
    """Score a merchant name for quality. Higher = better."""
    if not name or _is_garbage_merchant(name):
        return 0
    score = 10  # base score for non-garbage
    # Bonus for length (real names tend to be longer)
    score += min(len(name), 30)
    # Penalty for 3+ digit sequences (noise)
    if re.search(r'\d{3,}', name):
        score -= 30
    # Penalty for punctuation that's unusual in merchant names
    if re.search(r'[,;:><!?]', name):
        score -= 15
    # Bonus for recognizable business patterns
    if re.search(r'\b(?:RESTAURANT|TAVERN[AE]?|BAR|CAFE|OIL|PETROL|STATION|NOSH)\b', name, re.IGNORECASE):
        score += 20
    # Penalty for mixed-case garbage after entity words
    if re.search(r'\b(?:LTD|LLC|INC)\b.*[a-z]', name):
        score -= 15
    return score


def _extract_best(texts: list[str], filename: str) -> dict:
    """Parse multiple OCR texts and return the best combined extraction.

    Runs _parse_ocr_text on each text, then merges results:
    - Merchant: picked from earliest variant with non-garbage name (simpler preprocessing = more accurate text)
    - Amount/date: from the variant with most extracted fields, filled from others
    """
    if not texts:
        return _parse_ocr_text("", filename=filename)

    results = [_parse_ocr_text(t, filename=filename) for t in texts]

    # Pick merchant from earliest variant (original order, before sorting)
    # Earlier variants use simpler preprocessing → more accurate merchant names
    earliest_merchant = None
    for r in results:
        m = r.get('suggested_merchant')
        if m and not _is_garbage_merchant(m):
            earliest_merchant = m
            break

    def _score(r: dict) -> int:
        s = 0
        if r.get('suggested_amount') and r['suggested_amount'] > 0.05:
            s += 1
        if r.get('suggested_merchant') and not _is_garbage_merchant(r['suggested_merchant']):
            s += 1
        if r.get('suggested_year'):
            s += 1
        return s

    # Sort by completeness (most fields extracted first)
    results.sort(key=lambda r: -_score(r))
    merged = dict(results[0])

    for r in results[1:]:
        # Fill missing amount
        amt = r.get('suggested_amount')
        if (not merged.get('suggested_amount') or merged['suggested_amount'] <= 0.05) \
                and amt and amt > 0.05:
            merged['suggested_amount'] = amt
            merged['suggested_vat'] = r.get('suggested_vat')

        # Fill missing date
        if not merged.get('suggested_year') and r.get('suggested_year'):
            merged['suggested_year'] = r['suggested_year']
            merged['suggested_month'] = r.get('suggested_month')
            merged['suggested_day'] = r.get('suggested_day')
            d = r.get('suggested_date')
            if d:
                merged['suggested_date'] = d

    # Override merchant with earliest non-garbage name
    if earliest_merchant:
        merged['suggested_merchant'] = earliest_merchant
    elif _is_garbage_merchant(merged.get('suggested_merchant')):
        merged['suggested_merchant'] = None

    # Recalculate needs_review after merge
    merged['needs_review'] = (
        not merged.get('suggested_amount')
        or merged['suggested_amount'] <= 0.05
    )

    return merged


# ── Debug logging ──

def _log_extraction_debug(filename: str, method: str, result: dict,
                          raw_texts: list[str] | None = None):
    """Print comprehensive debug info for extraction of a single file."""
    print(f"\n{'='*60}")
    print(f"[OCR DEBUG] {filename}")
    print(f"  Method: {method}")

    # Amount candidates
    if raw_texts:
        all_amounts: list[tuple[float, str]] = []
        for t in raw_texts[:3]:  # limit to first 3 texts for debug
            amts = _extract_amounts(t)
            for a in amts:
                src = "standalone"
                if re.search(r'TOTAL|AMOUNT|SALE|PURCHASE|ΣΥΝΟΛΟ', t[:500], re.IGNORECASE):
                    src = "keyword"
                all_amounts.append((a, src))
        if all_amounts:
            print(f"  Amount candidates:")
            for a, src in all_amounts[:10]:
                print(f"    {a:.2f} ({src})")

    amt = result.get('suggested_amount')
    print(f"  Amount final: {f'{amt:.2f}' if amt else 'None'}")

    # Merchant candidates
    if raw_texts:
        merchants = []
        for t in raw_texts[:3]:
            m = _extract_merchant(t)
            if m:
                merchants.append(m)
        if merchants:
            print(f"  Merchant candidates: {merchants[:5]}")

    merch = result.get('suggested_merchant')
    print(f"  Merchant final: {merch!r}")

    # Date
    yr = result.get('suggested_year')
    mo = result.get('suggested_month')
    dy = result.get('suggested_day')
    if yr:
        src = "filename" if _parse_date_from_filename(filename) else "OCR text"
        print(f"  Date final: {yr}-{mo:02d}-{dy:02d} (source: {src})")
    else:
        print(f"  Date final: None")

    # Warnings
    if result.get('needs_review'):
        warnings = []
        if not amt or amt <= 0.05:
            warnings.append("no reliable amount")
        if not merch:
            warnings.append("no reliable merchant")
        if not yr:
            warnings.append("no date")
        print(f"  [!] needs_review=True: {', '.join(warnings)}")

    print(f"{'='*60}")


# ── Public API ──

def extract_from_image(image_path: Path, original_filename: str = "") -> dict:
    """Run OCR on an image and extract financial data.

    Uses multi-variant OCR: tries multiple preprocessing combinations
    and merges the best results across all variants.
    """
    from PIL import Image

    fname = original_filename or image_path.name
    img = Image.open(image_path)

    # Generate multiple OCR text variants
    texts = _generate_ocr_variants(img)

    if not texts:
        # Fallback to simple OCR
        raw = _ocr_with_retry(img)
        texts = [raw] if raw else []

    result = _extract_best(texts, filename=fname)
    result['raw_text'] = texts[0] if texts else ""

    _log_extraction_debug(fname, "OCR (image)", result, raw_texts=texts)
    return result


def extract_from_pdf(pdf_path: Path, original_filename: str = "") -> dict:
    """Extract text from PDF and parse financial data.

    Hybrid approach:
    1. Try pypdf text extraction first (fastest, most reliable for text PDFs)
    2. If pypdf text is missing amount or merchant, also try embedded image OCR
    3. Merge best results from both approaches
    """
    from pypdf import PdfReader

    fname = original_filename or pdf_path.name
    method = "PDF text"

    reader = PdfReader(str(pdf_path))
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)

    raw_text = "\n".join(text_parts).strip()
    all_texts: list[str] = []

    if raw_text:
        all_texts.append(raw_text)

    # Check if pypdf text is sufficient (has amount)
    primary_result = _parse_ocr_text(raw_text, filename=fname) if raw_text else None
    needs_image_ocr = (
        not primary_result
        or not primary_result.get('suggested_amount')
        or primary_result['suggested_amount'] <= 0.05
    )

    # Try embedded image OCR when text is insufficient
    if needs_image_ocr:
        method = "PDF text + image OCR (hybrid)"
        try:
            from PIL import Image

            for page in reader.pages:
                if hasattr(page, "images") and page.images:
                    for img_obj in page.images:
                        pil_img = Image.open(io.BytesIO(img_obj.data))
                        image_texts = _generate_ocr_variants(pil_img)
                        all_texts.extend(image_texts)
        except Exception as e:
            log.debug("pypdf image extraction failed: %s", e)

        # Also try pdf2image fallback
        if len(all_texts) <= 1:
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(str(pdf_path), first_page=1, last_page=1)
                if images:
                    image_texts = _generate_ocr_variants(images[0])
                    all_texts.extend(image_texts)
            except (ImportError, Exception) as e:
                log.debug("pdf2image fallback failed: %s", e)

    if not all_texts:
        result = _parse_ocr_text("", filename=fname)
        _log_extraction_debug(fname, method, result)
        return result

    result = _extract_best(all_texts, filename=fname)
    result['raw_text'] = all_texts[0]  # keep primary text

    _log_extraction_debug(fname, method, result, raw_texts=all_texts)
    return result


def _parse_date_from_filename(filename: str) -> tuple[int, int, int] | None:
    """Extract (year, month, day) from filename patterns like:

    - IMG20260124114731.jpg → (2026, 1, 24)
    - Scanned_20260108-0758.pdf → (2026, 1, 8)
    """
    m = re.search(r'(\d{4})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', filename)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2000 <= year <= 2099:
            return (year, month, day)
    return None


def _parse_ocr_text(raw_text: str, filename: str = "") -> dict:
    """Parse OCR text to extract financial data.

    Returns dict with:
        raw_text, suggested_amount, suggested_year, suggested_month,
        suggested_day, suggested_date, suggested_vat,
        suggested_client, suggested_merchant, suggested_invoice_number,
        needs_review
    """
    suggested_amount = None
    suggested_year = None
    suggested_month = None
    suggested_day = None
    suggested_date = None
    suggested_vat = None
    suggested_client = None
    suggested_merchant = None
    suggested_invoice_number = None
    needs_review = False

    if raw_text:
        amounts = _extract_amounts(raw_text)
        if amounts:
            suggested_amount = max(amounts)

        dates = _extract_dates(raw_text)

        # Filename date: prefer filename date as scan dates are more reliable than OCR
        fn_date = _parse_date_from_filename(filename) if filename else None
        if fn_date:
            dates = [fn_date]  # filename date always wins

        if dates:
            suggested_year, suggested_month, suggested_day = dates[0]
            suggested_date = f"{suggested_day:02d}/{suggested_month:02d}/{suggested_year}"

        suggested_vat = _extract_vat(raw_text)
        suggested_client = _extract_client_name(raw_text)
        suggested_merchant = _extract_merchant(raw_text)
        suggested_invoice_number = _extract_invoice_number(raw_text)
    else:
        # Even with no OCR text, try filename date
        fn_date = _parse_date_from_filename(filename) if filename else None
        if fn_date:
            suggested_year, suggested_month, suggested_day = fn_date
            suggested_date = f"{suggested_day:02d}/{suggested_month:02d}/{suggested_year}"

    # Flag for review when extraction is uncertain
    if not suggested_amount or suggested_amount <= 0.05:
        needs_review = True

    return {
        "raw_text": raw_text,
        "suggested_amount": suggested_amount,
        "suggested_year": suggested_year,
        "suggested_month": suggested_month,
        "suggested_day": suggested_day,
        "suggested_date": suggested_date,
        "suggested_vat": suggested_vat,
        "suggested_client": suggested_client,
        "suggested_merchant": suggested_merchant,
        "suggested_invoice_number": suggested_invoice_number,
        "needs_review": needs_review,
    }
