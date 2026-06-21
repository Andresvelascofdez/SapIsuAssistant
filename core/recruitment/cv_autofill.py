"""Rule-based CV autofill helpers for candidate forms."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

SECTION_HEADINGS = {
    "ABOUT ME",
    "ACADEMIC BACKGROUND",
    "CERTIFICATES",
    "CERTIFICATIONS",
    "CAREER SUMMARY",
    "CONTACT",
    "CONTACTO",
    "COURSES",
    "DATOS PERSONALES Y DE CONTACTO",
    "EDUCATION",
    "EMPLOYMENT HISTORY",
    "EXPERIENCE",
    "EXPERIENCIA",
    "EXPERIENCIA PROFESIONAL",
    "FORMATION",
    "FORMACION",
    "ESTUDIOS ACADEMICOS",
    "IDIOMAS",
    "INTERESTS",
    "KEY ACHIEVEMENTS",
    "LANGUAGES",
    "PERSONAL DETAILS",
    "PERSONAL INFORMATION",
    "PERFIL",
    "PROFILE",
    "PROFILE AND BACKGROUND",
    "NATIONALITY",
    "PROFESSIONAL EXPERIENCE",
    "PROFESSIONAL PROFILE",
    "PROFESSIONAL SUMMARY",
    "SAP CAREER SUMMARY",
    "SAP EXPERIENCE SUMMARY",
    "SAP EXPERIENCE - SUMMARY",
    "SIGNIFICANT PROJECTS",
    "SKILLS",
    "SUMMARY",
    "TECHNICAL KNOWLEDGE",
    "TECHNICAL SKILLS",
    "TECHNICAL SKILL SET",
    "TECHNOLOGIES",
    "TECNOLOGIAS",
    "TITULACION ACADEMICA",
    "WORK EXPERIENCE",
    "WORK EXPERIENCES",
    "WORK HISTORY",
}

SKILL_SECTION_HEADINGS = {
    "SAP CAREER SUMMARY",
    "SAP EXPERIENCE SUMMARY",
    "SAP EXPERIENCE - SUMMARY",
    "SKILLS",
    "TECHNICAL SKILLS",
    "TECHNICAL SKILL SET",
    "TECHNOLOGIES",
    "TECNOLOGIAS",
}
SKILL_STOP_HEADINGS = SECTION_HEADINGS - SKILL_SECTION_HEADINGS

LANGUAGE_SECTION_HEADINGS = {"LANGUAGES", "IDIOMAS"}

COUNTRY_NAMES = {
    "austria",
    "belgium",
    "bulgaria",
    "cyprus",
    "denmark",
    "france",
    "germany",
    "greece",
    "ireland",
    "italy",
    "luxembourg",
    "luxemburg",
    "netherlands",
    "poland",
    "portugal",
    "romania",
    "slovakia",
    "slovensko",
    "spain",
    "espana",
    "sweden",
    "turkey",
    "turkiye",
    "uk",
    "ukraine",
    "united kingdom",
    "usa",
    "portugal",
    "brazil",
    "brasil",
    "india",
}

PHONE_COUNTRY_PREFIXES = (
    ("351", "Portugal"),
    ("353", "Ireland"),
    ("30", "Greece"),
    ("34", "Spain"),
    ("33", "France"),
    ("39", "Italy"),
    ("40", "Romania"),
    ("421", "Slovakia"),
    ("46", "Sweden"),
    ("371", "Latvia"),
    ("359", "Bulgaria"),
    ("90", "Turkey"),
    ("48", "Poland"),
    ("54", "Argentina"),
    ("55", "Brazil"),
    ("38", "Ukraine"),
    ("91", "India"),
)

NAME_SKIP_RE = re.compile(
    r"(@|https?://|linkedin|resume|curriculum|cv\b|phone|email|\brate\b|years?|"
    r"location|address|website|certified|certificate|associate|application|"
    r"development|professional|platform|modeling|spring|summary|license|"
    r"history|experience|expertise|knowledge|formation|education|academic|"
    r"marketing|module|profile|overview|across|industries|work\s+history|"
    r"performance|improvement|resolution|motivated|collaboration|listening|"
    r"decision|teambuilding|adaptable|personal\s+details|"
    r"native|fluent|advanced|intermediate|professional\s+working|language|languages|"
    r"titulacion|formacion|technical\s+knowledge|material|ledger|dictionary|project|"
    r"proyecto|client|company|solution|solutions|pvt|ltd|university|"
    r"universidad|administracion|administration|bases|datos|database|"
    r"insurance|pharmaceuticals|bank|automotive|aerospace|defence|"
    r"telecom|olivetti|rome|roma|lazio|"
    r"avante|\bit\b|viewnext|inetum|accenture|capgemini|group|requirement|"
    r"requirements|specification|specifications)",
    re.I,
)
ROLE_WORD_RE = re.compile(
    r"\b(consultant|developer|architect|engineer|manager|analyst|specialist|"
    r"administrator|lead|director|head|functional|technical|abap|fiori|"
    r"programador|consultor|desarrollador|analista|project\s+manager|"
    r"solution\s+architect|delivery|operations)\b",
    re.I,
)
SENIORITY_ORDER = ("Senior", "Lead", "Architect", "Consultant", "Developer", "Mid", "Junior")
NAME_PARTICLES = {"de", "del", "da", "das", "dos", "di", "du", "la", "le", "van", "von", "y"}


def autofill_from_text(text: str, filename_hint: str | None = None) -> dict[str, str | float]:
    raw_content = text or ""
    lines = _lines(raw_content)
    content = "\n".join(lines)
    data: dict[str, str | float] = {}

    email = _extract_email(content)
    if email:
        data["email"] = email

    phone = _extract_phone(content)
    if phone:
        data["phone"] = phone

    linkedin = _extract_linkedin(lines, content)
    if linkedin:
        data["linkedin"] = linkedin

    location = _infer_location(lines)
    if "country" not in location:
        country = _infer_country_from_phone(phone) or _infer_country_from_nearby_text(lines)
        if country:
            location["country"] = country
    data.update(location)

    identity = _infer_identity(lines)
    filename_name = _infer_name_from_filename(filename_hint or "")
    linkedin_name = _infer_name_from_linkedin(linkedin)
    if identity.get("full_name"):
        data["full_name"] = identity["full_name"]
    elif linkedin_name:
        data["full_name"] = linkedin_name
    elif filename_name:
        data["full_name"] = filename_name

    strong_labeled_role = _infer_labeled_role(lines, strong_only=True)
    labeled_role = _infer_labeled_role(lines)
    role = (
        strong_labeled_role
        or identity.get("main_role")
        or labeled_role
        or _infer_first_role_line(lines)
        or _infer_role_from_filename(filename_hint or "")
    )
    if role:
        data["main_role"] = role

    seniority = _infer_seniority(content, role=role, lines=lines)
    if seniority:
        data["seniority"] = seniority

    years = _infer_years_experience(content)
    if years:
        data["years_experience"] = years

    work_mode = _infer_work_mode(content)
    if work_mode and "work_mode" not in data:
        data["work_mode"] = work_mode

    skills = _extract_skills(lines)
    if skills:
        data["skills"] = ", ".join(skills)

    sap_modules = _extract_sap_modules(skills, role)
    if sap_modules:
        data["sap_modules"] = ", ".join(sap_modules)

    languages = _extract_languages(lines)
    if languages:
        data["languages"] = ", ".join(languages)

    rates = _infer_rates(content)
    data.update(rates)

    currency = _infer_currency(content)
    if currency:
        data["currency"] = currency

    return data


def _first_match(pattern: str, text: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    return match.group(0).strip(" .,:;") if match else ""


def _lines(text: str) -> list[str]:
    return [
        normalized.strip(" \t-|*")
        for line in text.splitlines()
        if (normalized := _normalize_spaced_ocr_line(line.strip()))
    ]


def _normalize_spaced_ocr_line(line: str) -> str:
    if not line:
        return ""
    tokens = line.split()
    if len(tokens) >= 6:
        single_count = sum(1 for token in tokens if len(token) == 1)
        if single_count / len(tokens) >= 0.65:
            words = ["".join(part.split()) for part in re.split(r"\s{2,}", line) if part.strip()]
            collapsed = " ".join(words)
            collapsed = re.sub(r":", ": ", collapsed)
            return collapsed.strip()
    line = re.sub(r"\s+([@._-])\s+", r"\1", line)
    line = re.sub(r"\(\s*\+\s*(\d(?:\s+\d){1,2})\s*\)", lambda m: "(+" + m.group(1).replace(" ", "") + ")", line)
    return re.sub(r"\s+", " ", line).strip()


def _extract_email(text: str) -> str:
    lines = _lines(text)
    for index, line in enumerate(lines):
        normalized = _normalize_email_line(line)
        if "@" in normalized and index + 1 < len(lines):
            next_line = re.sub(r"[^A-Za-z]", "", lines[index + 1])
            if re.fullmatch(r"[A-Za-z]{2,4}", next_line or ""):
                normalized = normalized.rstrip(" .") + next_line
        email = _first_match(r"[\w.+-]+@[\w-]+(?:\.[A-Za-z]{2,24})+", normalized)
        if email:
            return _clean_email(email)
    return ""


def _normalize_email_line(line: str) -> str:
    normalized = re.sub(r"\s*@\s*", "@", line)
    normalized = re.sub(r"(?<=\w)\s*\.\s*(?=\w)", ".", normalized)
    return normalized


def _clean_email(email: str) -> str:
    clean = re.sub(r"(Tel|Phone|Mobile)$", "", email, flags=re.I)
    clean = re.sub(r"\.com(?:tel|phone|mobile)$", ".com", clean, flags=re.I)
    clean = re.sub(r"\.net(?:tel|phone|mobile)$", ".net", clean, flags=re.I)
    clean = re.sub(r"\.org(?:tel|phone|mobile)$", ".org", clean, flags=re.I)
    return clean.strip(" .,:;")


def _extract_linkedin(lines: list[str], text: str) -> str:
    for line in lines[:90]:
        if "linkedin" not in line.lower():
            continue
        value = re.sub(r"^.*linkedin\s*[:\-]?\s*", "", line, flags=re.I).strip()
        for candidate in _linkedin_candidates(value, lines, line):
            linkedin = _match_linkedin(candidate)
            if linkedin:
                return linkedin
    for index, line in enumerate(lines[:90]):
        if "linkedin.com/" not in line.lower():
            continue
        for candidate in _linkedin_candidates(line, lines, line, index):
            linkedin = _match_linkedin(candidate)
            if linkedin:
                return linkedin
    linkedin = _match_linkedin(text)
    if linkedin:
        return linkedin
    return ""


def _linkedin_candidates(value: str, lines: list[str], line: str, known_index: int | None = None) -> list[str]:
    try:
        index = lines.index(line) if known_index is None else known_index
    except ValueError:
        index = -1
    value = re.split(r"\b(?:Email|E-mail|Phone|Contact|Tel)\b", value, maxsplit=1, flags=re.I)[0].strip()
    candidates: list[str] = []
    if index >= 0 and index + 1 < len(lines):
        nxt = re.sub(r"\s*\(LinkedIn\)\s*", "", lines[index + 1], flags=re.I).strip()
        if nxt and not _is_section_heading(nxt):
            candidates.extend([value + nxt, value.rstrip("/-") + "-" + nxt.lstrip("/-")])
    candidates.append(value)
    return candidates


def _match_linkedin(value: str) -> str:
    clean = re.sub(r"\s+", "", value or "")
    clean = clean.replace("\uf0e1", "").replace("🔗", "")
    match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/(?:i?n/|in/)[A-Za-z0-9._%-]+", clean, re.I)
    if match:
        url = match.group(0)
        url = re.sub(r"linkedin\.com/i?n/", "linkedin.com/in/", url, flags=re.I)
        return url.rstrip(".,;:)")
    partial = re.search(r"\bin/[A-Za-z0-9._%-]+", clean)
    if partial:
        return "https://www.linkedin.com/" + partial.group(0).rstrip(".,;:)")
    return ""


def _infer_location(lines: list[str]) -> dict[str, str]:
    for line in lines[:100]:
        match = re.match(r"^(location|ubicacion|city|address)\s*[:\-]?\s*(.+)$", _strip_accents(line), re.I)
        if match:
            value = line.split(":", 1)[-1] if ":" in line else match.group(2)
            if value.strip().startswith(("/", "\\")):
                continue
            if match.group(1).lower() == "address" and not _looks_like_location_line(value):
                continue
            return _parse_location(value, allow_unknown_country=True)

    for line in lines[:35]:
        segment = _location_segment_from_contact_line(line)
        if segment and _looks_like_location_line(segment):
            return _parse_location(segment)

    for line in lines[:20]:
        if _looks_like_location_line(line):
            return _parse_location(line)
    return {}


def _location_segment_from_contact_line(line: str) -> str:
    if "," not in line:
        return ""
    segment = re.split(r"\s(?:\||/|\u00b7)\s|[\t]", line, maxsplit=1)[0]
    segment = re.split(r"\+?\d[\d\s().-]{6,}|[\w.+-]+@[\w-]+", segment, maxsplit=1)[0]
    return segment.strip(" ,.;")


def _parse_location(value: str, allow_unknown_country: bool = False) -> dict[str, str]:
    clean = re.sub(r"\s+", " ", value).strip(" ,.;")
    clean = re.sub(r"\([^)]*(?:remote|onsite|on-site|hybrid|fully remote)[^)]*\)", "", clean, flags=re.I).strip(" ,.;")
    if not clean:
        return {}
    remote = re.match(r"^remote\s*(?:\((?P<timezone>[^)]+)\))?", clean, re.I)
    if remote:
        result = {"work_mode": "Remote"}
        if remote.group("timezone"):
            result["timezone"] = re.sub(r"\s*/\s*", "/", remote.group("timezone").strip())
        return result
    parenthetical = re.match(r"^(?P<city>.+?)\s*\((?P<country>[^)]+)\)\s*$", clean)
    if parenthetical:
        country = parenthetical.group("country").strip(" ,")
        if _country_key(country) in COUNTRY_NAMES:
            return {"city": parenthetical.group("city").strip(" ,"), "country": _canonical_country_name(country)}
    if "," in clean:
        parts = [part.strip() for part in clean.split(",") if part.strip()]
        if len(parts) >= 2:
            first_key = _country_key(parts[0])
            last_key = _country_key(parts[-1])
            if first_key in COUNTRY_NAMES:
                return {"country": _canonical_country_name(parts[0]), "city": parts[-1]}
            if last_key in COUNTRY_NAMES:
                return {"city": parts[0], "country": _canonical_country_name(parts[-1])}
            if allow_unknown_country:
                return {"city": parts[0], "country": parts[-1]}
    dash = re.match(r"^(?P<city>[A-Za-zÀ-ÿ .'-]{2,})-(?P<code>[A-Za-z]{2})$", clean)
    if dash:
        country = _country_from_code(dash.group("code"))
        if country:
            return {"city": dash.group("city").strip(), "country": country}
    return {"city": clean}


def _looks_like_location_line(line: str) -> bool:
    clean = _clean_role(line)
    if not clean or len(clean) > 90:
        return False
    lower = clean.lower()
    if re.search(r"\d|@|phone|email|linkedin|developer|consultant|abap|sap|ricefw|profile|project", lower, re.I):
        return False
    if clean.count(" ") > 5:
        return False
    if "," in clean:
        parts = [part.strip() for part in clean.split(",") if part.strip()]
        if 2 <= len(parts) <= 3 and (_country_key(parts[0]) in COUNTRY_NAMES or _country_key(parts[-1]) in COUNTRY_NAMES):
            return True
    parenthetical = re.match(r"^(.+?)\s*\(([^)]+)\)$", clean)
    return bool(parenthetical and _country_key(parenthetical.group(2)) in COUNTRY_NAMES)


def _infer_identity(lines: list[str]) -> dict[str, str]:
    for index, line in enumerate(lines[:140]):
        if _is_section_heading(line) or _is_labeled_line(line):
            labeled = _identity_from_labeled_name_line(line, lines, index)
            if labeled:
                return labeled
            continue
        labeled = _identity_from_labeled_name_line(line, lines, index)
        if labeled:
            return labeled
        email_identity = _identity_from_email_line(line, lines, index)
        if email_identity:
            return email_identity
        split_identity = _split_identity_line(line)
        if split_identity:
            return split_identity
        if _looks_like_name(line):
            role = _find_role_after_name(lines, index)
            return {"full_name": _clean_name(line), "main_role": role}

    for index, line in enumerate(lines[:240]):
        if _looks_like_strong_name(line):
            return {"full_name": _clean_name(line), "main_role": _find_role_after_name(lines, index)}
    return {}


def _identity_from_labeled_name_line(line: str, lines: list[str], index: int) -> dict[str, str] | None:
    normalized = _strip_accents(line)
    label_re = r"^(surname\s*/\s*name|surname\s+/\s+name|nombre\s+y\s+apellidos|full\s+name|name|nombre)\b"
    if not re.match(label_re, normalized, re.I):
        return None
    parts = [part.strip() for part in re.split(r"\||:", line) if part.strip()]
    for part in parts[1:] or parts:
        part = re.sub(label_re, "", part, flags=re.I).strip(" :|-")
        part = _normalize_surname_name_value(part)
        if _looks_like_name(part):
            return {"full_name": _clean_name(part), "main_role": _find_role_after_name(lines, index)}
    return None


def _normalize_surname_name_value(value: str) -> str:
    clean = re.sub(r"\s+", " ", value).strip(" ,.;")
    if "/" not in clean:
        return clean
    left, right = [part.strip() for part in clean.split("/", 1)]
    if left and right and _has_letter(left) and _has_letter(right):
        return f"{right} {left}"
    return clean


def _identity_from_email_line(line: str, lines: list[str], index: int) -> dict[str, str] | None:
    if "@" not in line:
        return None
    email = _extract_email(line)
    if not email:
        return None
    prefix = line.split(email.split("@")[0], 1)[0].strip()
    if _looks_like_name(prefix):
        return {"full_name": _clean_name(prefix), "main_role": _find_role_after_name(lines, index)}
    return None


def _split_identity_line(line: str) -> dict[str, str] | None:
    comma_parts = [part.strip() for part in line.split(",", 1)]
    if len(comma_parts) == 2 and _looks_like_name(comma_parts[0]) and _looks_like_role_line(comma_parts[1]):
        return {"full_name": _clean_name(comma_parts[0]), "main_role": _clean_role(comma_parts[1])}

    spaced_parts = re.split(r"\s{2,}", line, maxsplit=1)
    if len(spaced_parts) == 2 and _looks_like_name(spaced_parts[0]) and _looks_like_role_line(spaced_parts[1]):
        return {"full_name": _clean_name(spaced_parts[0]), "main_role": _clean_role(spaced_parts[1])}

    sap_role = re.match(r"^(?P<name>.+?)\s+(?P<role>SAP\b.+)$", line, re.I)
    if sap_role and _looks_like_name(sap_role.group("name")) and _looks_like_role_line(sap_role.group("role")):
        return {"full_name": _clean_name(sap_role.group("name")), "main_role": _clean_role(sap_role.group("role"))}

    return None


def _find_role_after_name(lines: list[str], name_index: int) -> str:
    role_parts: list[str] = []
    skipped = 0
    for candidate in lines[name_index + 1:name_index + 14]:
        if _is_section_heading(candidate):
            if role_parts:
                break
            skipped += 1
            continue
        if _is_labeled_line(candidate) or _looks_like_location_line(candidate):
            skipped += 1
            continue
        if role_parts and len(candidate) <= 35 and candidate.upper() == candidate and _has_letter(candidate):
            role_parts.append(_clean_role(candidate))
            continue
        if _looks_like_role_line(candidate) or (not role_parts and _looks_like_title_line(candidate)):
            if role_parts:
                break
            role = _clean_role_for_main(candidate)
            if role:
                role_parts.append(role)
            else:
                skipped += 1
            continue
        if _looks_like_years_line(candidate):
            skipped += 1
            continue
        skipped += 1
        if role_parts or skipped >= 8:
            break
    return " ".join(role_parts).strip()


def _infer_labeled_role(lines: list[str], strong_only: bool = False) -> str:
    for line in lines[:100]:
        normalized = line.replace("\u2013", "-").replace("\u2014", "-")
        match = re.match(r"^(position|role|main role|professional profile|job\s+or\s+function|puesto|ocupacion)\b", normalized, re.I)
        if not match:
            continue
        if strong_only and match.group(1).lower() == "role":
            continue
        remainder = normalized[match.end():].strip(" :|-")
        parts = [part.strip() for part in re.split(r"\|", remainder) if part.strip()]
        role = _clean_role(parts[0] if parts else remainder)
        if "." in role:
            role = role.split(".", 1)[0].strip()
        if _looks_like_role_line(role) or _looks_like_title_line(role):
            return role
    return ""


def _infer_first_role_line(lines: list[str]) -> str:
    for line in lines[:160]:
        if _is_section_heading(line) or _is_labeled_line(line) or _looks_like_location_line(line):
            continue
        if not _looks_like_role_line(line):
            continue
        role = _clean_role_for_main(line)
        if role:
            return role
    return ""


def _clean_role_for_main(value: str) -> str:
    role = _clean_role(value)
    if "@" in role or re.search(r"https?://|linkedin", role, re.I):
        return ""
    if re.match(r"^(i\s+am|i\s+have|this\s+candidate|candidate\s+has|over\s+all|overall)\b", role, re.I):
        return ""
    if role[:1].islower():
        return ""
    if "|" in role and re.match(r"^(responsibilities|responsabilities|duties|tasks)\b", role, re.I):
        role = role.split("|", 1)[1].strip()
    role = re.split(r"\b(?:assigned|asignado|destinado|based on|responsible for|description)\b", role, maxsplit=1, flags=re.I)[0]
    role = re.split(
        r"\b(?:with\s+over|with\s+\d{1,2}\+?\s+years?|with\s+\d|over\s+\d{1,2}\s+years?|more\s+than\s+\d{1,2}\s+years?)\b",
        role,
        maxsplit=1,
        flags=re.I,
    )[0]
    role = re.split(
        r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december|"
        r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b",
        role,
        maxsplit=1,
        flags=re.I,
    )[0]
    role = re.split(r",\s*(?:en|in)\s+|\s+en\s+diferentes\b|\s+in\s+different\b", role, maxsplit=1, flags=re.I)[0]
    role = re.split(r",\s*(?:remote|hybrid|onsite|on-site)\b", role, maxsplit=1, flags=re.I)[0]
    role = re.sub(r"^(role|position)\s*[:\-]\s*", "", role, flags=re.I)
    role = role.strip(" ,.;:-")
    if len(role) > 110:
        role = role[:110].rsplit(" ", 1)[0].strip(" ,.;:-")
    if _looks_like_role_line(role) or _looks_like_title_line(role):
        return role
    return ""


def _clean_name(value: str) -> str:
    clean = re.sub(r"\s*\([^)]*(?:\d{1,3}|ans|years?|yrs?)[^)]*\)\s*$", "", value, flags=re.I)
    return re.sub(r"\s+", " ", clean).strip(" ,.;")


def _clean_role(value: str) -> str:
    value = value.replace("\u2022", " ")
    return re.sub(r"\s+", " ", value).strip(" ,.;")


def _looks_like_name(value: str) -> bool:
    clean = _clean_name(value)
    if not clean or _is_section_heading(clean) or NAME_SKIP_RE.search(_strip_accents(clean)):
        return False
    if any(char.isdigit() for char in clean):
        return False
    if any(mark in clean for mark in ("/", "|", ":", ",", "@")):
        return False
    if clean.upper().startswith("SAP "):
        return False
    if ROLE_WORD_RE.search(clean):
        return False
    words = clean.replace("-", " ").split()
    if not (2 <= len(words) <= 5):
        return False
    if not all(_has_letter(word) for word in words):
        return False
    return _has_name_capitalization(words)


def _looks_like_strong_name(value: str) -> bool:
    clean = _clean_name(value)
    words = clean.split()
    return _looks_like_name(clean) and (clean.upper() == clean or all(word[:1].isupper() for word in words if word.lower() not in NAME_PARTICLES))


def _has_name_capitalization(words: list[str]) -> bool:
    joined = " ".join(words)
    if joined.upper() == joined:
        return True
    for word in words:
        if word.lower() in NAME_PARTICLES:
            continue
        if not word[:1].isupper():
            return False
    return True


def _looks_like_role_line(value: str) -> bool:
    clean = _clean_role(value)
    if not clean or _is_labeled_line(clean):
        return False
    if len(clean) > 150:
        return False
    if re.match(r"^(technical skill set|skills|built|implemented|configured|developed|managed|supported)\b", clean, re.I):
        return False
    return bool(ROLE_WORD_RE.search(clean))


def _looks_like_title_line(value: str) -> bool:
    clean = _clean_role(value)
    if not clean or len(clean) > 110 or _is_labeled_line(clean) or _is_section_heading(clean):
        return False
    if any(char.isdigit() for char in clean):
        return False
    words = clean.split()
    if not 2 <= len(words) <= 11:
        return False
    title_markers = ("SAP", "Operations", "Project", "Delivery", "Enterprise", "Cloud", "Technical", "Process", "FICO", "FI", "CO")
    return any(marker.lower() in clean.lower() for marker in title_markers)


def _looks_like_years_line(value: str) -> bool:
    return bool(re.search(r"\b\d{1,2}\+?\s*(years|yrs)\b|\byears?\s+of\s+experience\b", value, re.I))


def _is_labeled_line(line: str) -> bool:
    normalized = _strip_accents(line).lower()
    return bool(
        re.match(
            r"^(contact\s+no|contact|phone|phone number|email|e-mail|location|ubicacion|linkedin|website|"
            r"address|telefono|tel|company|client|industry|nationality|birthdate|date\s+of\s+birth|"
            r"dni|fecha\s+de\s+nacimiento|position|role|main\s+role|professional\s+profile|"
            r"job\s+or\s+function|puesto|ocupacion)\b",
            normalized,
            re.I,
        )
    )


def _is_section_heading(line: str) -> bool:
    return _section_key(line) in SECTION_HEADINGS


def _section_key(line: str) -> str:
    return re.sub(r"\s+", " ", _strip_accents(line)).strip(" :").upper()


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _country_key(value: str) -> str:
    clean = re.sub(r"[^A-Za-zÀ-ÿ ]+", " ", _strip_accents(value))
    return re.sub(r"\s+", " ", clean).strip().lower()


def _country_from_code(code: str) -> str:
    return {
        "PT": "Portugal",
        "ES": "Spain",
        "BR": "Brazil",
        "IE": "Ireland",
        "FR": "France",
        "GR": "Greece",
        "IT": "Italy",
        "RO": "Romania",
        "SE": "Sweden",
        "IN": "India",
    }.get(code.upper(), "")


def _canonical_country_name(value: str) -> str:
    key = _country_key(value)
    return {
        "espana": "Spain",
        "spain": "Spain",
        "portugal": "Portugal",
        "pt": "Portugal",
        "brasil": "Brazil",
        "brazil": "Brazil",
        "france": "France",
        "greece": "Greece",
        "romania": "Romania",
        "ireland": "Ireland",
        "india": "India",
        "italy": "Italy",
        "sweden": "Sweden",
    }.get(key, re.sub(r"[^A-Za-zÀ-ÿ ]+", "", value).strip() or value.strip())


def _infer_country_from_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if phone.strip().startswith("+") or phone.strip().startswith("00"):
        if digits.startswith("00"):
            digits = digits[2:]
        for prefix, country in PHONE_COUNTRY_PREFIXES:
            if digits.startswith(prefix):
                return country
        return ""
    if len(digits) == 9 and digits[0] in {"6", "7", "9"}:
        return "Spain"
    return ""


def _infer_country_from_nearby_text(lines: list[str]) -> str:
    window = "\n".join(lines[:60])
    if re.search(r"\b(Madrid|Sevilla|Barcelona|Spain|Espa(?:n|ñ)a)\b", window, re.I):
        return "Spain"
    if re.search(r"\bLisboa|Portugal\b", window, re.I):
        return "Portugal"
    if re.search(r"\bAthens|Greece\b", window, re.I):
        return "Greece"
    if re.search(r"\bRome|Roma|Italy|Lazio\b", window, re.I):
        return "Italy"
    if re.search(r"\bSweden\b", window, re.I):
        return "Sweden"
    return ""


def _has_letter(value: str) -> bool:
    return any(char.isalpha() for char in value)


def _infer_seniority(text: str, role: str = "", lines: list[str] | None = None) -> str:
    candidates = [role]
    if lines:
        candidates.append("\n".join(lines[:12]))
    for source in candidates:
        if not source:
            continue
        if re.search(r"\bmid[- ]level\b", source, re.I):
            return "Mid"
        for label in SENIORITY_ORDER:
            if re.search(rf"\b{re.escape(label)}\b", source, re.I):
                return label
    return ""


def _infer_years_experience(text: str) -> str:
    number = r"(\d{1,2}(?:[,.]\d+)?)"
    normalized = re.sub(r"\+(\d)\s+(\d)\s*(years|yrs)\b", r"\1\2+ \3", text, flags=re.I)
    normalized = re.sub(r"\b(\d)\s+(\d)\+\s*(years|yrs)\b", r"\1\2+ \3", normalized, flags=re.I)
    priority_patterns = (
        (rf"\b(?:with\s+)?over\s+{number}\s*(?:years|yrs)(?:\s+of\s+experience)?\b", "over {value} years"),
        (rf"\bwith\s+{number}\s*(?:years|yrs)\s+of\s+experience\b", "{value} years"),
        (rf"\b{number}\s*(?:years|yrs)\s+of\s+(?:professional\s+)?experience\b", "{value} years"),
    )
    priority_matches: list[tuple[int, str, str]] = []
    for pattern, template in priority_patterns:
        for match in re.finditer(pattern, normalized, re.I):
            value = match.group(1).replace(",", ".")
            priority_matches.append((match.start(), template, value))
    if priority_matches:
        _, template, value = min(priority_matches, key=lambda item: item[0])
        return template.format(value=value)
    patterns = (
        (rf"\bover\s+{number}\s*(?:years|yrs)\b", "over {value} years"),
        (rf"\b{number}\+\s*(?:years|yrs)\b", "{value}+ years"),
        (rf"\b{number}\s*(?:years|yrs)\s+(?:of\s+)?experience\b", "{value} years"),
        (rf"\b{number}\s*(?:years|yrs)\b", "{value} years"),
    )
    for pattern, template in patterns:
        match = re.search(pattern, normalized, re.I)
        if match:
            value = match.group(1).replace(",", ".")
            return template.format(value=value)
    return ""


def _infer_work_mode(text: str) -> str:
    lower = text.lower()
    if "remote" in lower:
        return "Remote"
    if "hybrid" in lower:
        return "Hybrid"
    if "onsite" in lower or "on-site" in lower:
        return "Onsite"
    return ""


def _extract_skills(lines: list[str]) -> list[str]:
    skills: list[str] = []
    collecting = False
    for line in lines:
        normalized = _section_key(line).replace("\u2013", "-")
        if normalized in SKILL_SECTION_HEADINGS:
            collecting = True
            continue
        if collecting and (
            normalized in SKILL_STOP_HEADINGS
            or normalized.startswith("PAGE ")
            or normalized in {"PROFILE", "EMPLOYMENT HISTORY", "PERSONAL INFORMATION"}
            or re.search(r"\bWORK EXPERIENCES?\b", normalized)
            or normalized.endswith(" EXPERIENCE")
        ):
            break
        if collecting and len(skills) >= 5 and _looks_like_experience_sentence(line):
            break
        if collecting and len(skills) >= 3 and _looks_like_name(line):
            break
        if not collecting and re.match(r"^TECHNICAL SKILL SET\s*:", line, re.I):
            collecting = True
            inline = re.sub(r"^TECHNICAL SKILL SET\s*:\s*", "", line, flags=re.I)
            for part in re.split(r"[,;|]", inline):
                skill = _clean_skill_line(part)
                if skill:
                    skills.append(skill)
            continue
        if not collecting:
            continue
        if re.match(r"^(core|herramientas|informes|integracion|calidad|nuevas tecnologias)\b", _strip_accents(line), re.I):
            line = line.split(":", 1)[-1]
            for part in re.split(r"[,;]", line):
                skill = _clean_skill_line(part)
                if skill:
                    skills.append(skill)
            continue
        skill = _clean_skill_line(line)
        if skill:
            skills.append(skill)
        if len(skills) >= 35:
            break
    return _dedupe(skills)


def _extract_languages(lines: list[str]) -> list[str]:
    languages: list[str] = []
    collecting = False
    for line in lines:
        normalized = _section_key(line)
        if normalized in LANGUAGE_SECTION_HEADINGS:
            collecting = True
            continue
        labeled = re.match(r"^(languages?\s+known|languages|idiomas)\s*[:\-]\s*(.+)$", line, re.I)
        if labeled:
            languages.extend(_split_language_line(labeled.group(2)))
            continue
        if collecting and normalized in SECTION_HEADINGS:
            break
        if collecting:
            if _looks_like_experience_sentence(line) or re.search(r"\b(SAP|ABAP|JavaScript|Python|HTML|CSS|OData|CDS)\b", line):
                break
            languages.extend(_split_language_line(line))
        if len(languages) >= 12:
            break
    return _dedupe([language for language in languages if language])


def _split_language_line(line: str) -> list[str]:
    clean = re.sub(r"[•\u25aa›▸]", " ", line)
    clean = re.sub(r"\s+", " ", clean).strip(" .;")
    if not clean:
        return []
    parts = re.split(r"\s{2,}|;|\|", clean)
    if len(parts) == 1 and len(clean.split()) > 5:
        parts = re.split(r"(?=\b(?:English|Spanish|French|Portuguese|German|Hindi|Bengali|Italian|Romanian|Turkish)\b)", clean, flags=re.I)
    results: list[str] = []
    for part in parts:
        value = part.strip(" ,.;:-")
        if not value:
            continue
        if re.search(r"\b(native|fluent|advanced|intermediate|professional|working|b1|b2|c1|c2|a1|a2|basico|basic|mother tongue)\b", value, re.I):
            results.append(value)
        elif re.fullmatch(r"(English|Spanish|French|Portuguese|German|Hindi|Bengali|Italian|Romanian|Turkish)", value, re.I):
            results.append(value)
    return results


def _clean_skill_line(line: str) -> str:
    clean = line.strip(" \t-*|\u2022\u25aa\uf0b7o")
    clean = re.sub(r"^[\u25aa\u2022\uf0b7]\s*", "", clean)
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"\s*\(?\d{1,2}(?:[,.]\d+)?\+?\s*(?:years|year|yrs|yr)\)?$", "", clean, flags=re.I)
    clean = clean.strip(" ,.;")
    if not clean or len(clean) > 95:
        return ""
    if clean.lower() in {"native", "fluent", "professional proficiency", "driving license"}:
        return ""
    if _is_section_heading(clean):
        return ""
    return clean


def _looks_like_experience_sentence(line: str) -> bool:
    clean = line.strip()
    if not clean:
        return False
    if re.match(r"^(built|developed|led|reduced|optimized|implemented|managed|coordinated|collaborated|supported)\b", clean, re.I):
        return True
    return len(clean.split()) >= 9 and clean.endswith(".")


def _extract_sap_modules(skills: list[str], role: str) -> list[str]:
    candidates: list[str] = []
    for source in [role, *skills]:
        if re.search(r"\bSAP\b|S/4|HANA|FI-CA|IS-U", source, re.I):
            candidates.append(_clean_sap_module(source))
    return _dedupe([candidate for candidate in candidates if candidate])


def _clean_sap_module(value: str) -> str:
    clean = re.sub(r"\b(functional|technical|senior|junior|lead|developer|consultant|architect|manager)\b", "", value, flags=re.I)
    clean = re.sub(r"\s+", " ", clean).strip(" ,/.;-")
    return clean or value.strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _infer_rates(text: str) -> dict[str, float]:
    data: dict[str, float] = {}
    euro = re.escape(chr(0x20AC))
    pound = re.escape(chr(0x00A3))
    number = r"(\d+(?:[.,]\d+)?)"
    currency = rf"(?:EUR|USD|GBP|{euro}|\$|{pound})?"
    hourly_patterns = (
        rf"(?:hourly\s+rate\s*){currency}\s*{number}",
        rf"{currency}\s*{number}\s*(?:EUR|USD|GBP)?\s*(?:/|per\s*)?(?:h|hr|hour)\b",
        rf"{number}\s*(?:EUR|USD|GBP)\s*(?:/|per\s*)?(?:h|hr|hour)\b",
    )
    daily_patterns = (
        rf"(?:daily\s+rate\s*){currency}\s*{number}",
        rf"{currency}\s*{number}\s*(?:EUR|USD|GBP)?\s*(?:/|per\s*)?(?:d|day)\b",
        rf"{number}\s*(?:EUR|USD|GBP)\s*(?:/|per\s*)?(?:d|day)\b",
    )
    hourly = _first_rate(hourly_patterns, text)
    if hourly is not None:
        data["rate_hour"] = hourly
    daily = _first_rate(daily_patterns, text)
    if daily is not None:
        data["rate_day"] = daily
    return data


def _first_rate(patterns: tuple[str, ...], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1).replace(",", "."))
    return None


def _infer_currency(text: str) -> str:
    currency_context = re.compile(r"(hourly\s+rate|daily\s+rate|/h\b|/hr\b|/hour\b|/d\b|/day\b|per\s+hour|per\s+day|currency)", re.I)
    for line in _lines(text):
        if not currency_context.search(line):
            continue
        if re.search(rf"\bEUR\b|{re.escape(chr(0x20AC))}|\beuro\b", line, re.I):
            return "EUR"
        if re.search(r"\bUSD\b|\$", line, re.I):
            return "USD"
        if re.search(rf"\bGBP\b|{re.escape(chr(0x00A3))}", line, re.I):
            return "GBP"
    return ""


def _extract_phone(text: str) -> str:
    lines = _lines(text)
    for index, line in enumerate(lines[:90]):
        if line.strip() == "+" and index + 1 < len(lines):
            combined = "+" + " ".join(lines[index + 1:index + 3])
            phone = _phone_from_line(combined)
            if phone:
                return phone
    for line in lines[:90]:
        if re.match(r"^(phone|phone number|telefono|tel)\b", _strip_accents(line), re.I):
            value = re.sub(r"^(phone number|phone|telefono|tel)\s*[:\-]?\s*", "", _strip_accents(line), flags=re.I)
            phone = _phone_from_line(value)
            if phone:
                return phone
        if "phone:" in line.lower():
            value = re.sub(r"^.*phone\s*:\s*", "", line, flags=re.I)
            phone = _phone_from_line(value)
            if phone:
                return phone
    for line in lines[:80]:
        phone = _phone_from_line(line, require_plus=True)
        if phone:
            return phone
    for line in lines[:90]:
        if _looks_like_standalone_phone_line(line):
            phone = _phone_from_line(line)
            if phone:
                return phone
    return ""


def _looks_like_standalone_phone_line(line: str) -> bool:
    if "@" in line or re.search(r"\b(page|year|sap|hana|abap|cds)\b", line, re.I):
        return False
    stripped = line.strip()
    digits = re.sub(r"\D", "", stripped)
    return 7 <= len(digits) <= 16 and bool(re.fullmatch(r"[+()0-9 .-]+", stripped)) and not _is_date_like(stripped)


def _phone_from_line(line: str, require_plus: bool = False) -> str:
    line = re.sub(r"\(\s*\+(\d{1,3})\s*\)", r"+\1 ", line)
    chunks = re.split(r"[|]", line)
    pattern = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s().-]*)?(?:\(?\d{2,4}\)?[\s.-]*){1,5}\d{2,4}(?!\d)")
    for chunk in chunks:
        if require_plus and "+" not in chunk:
            continue
        for match in pattern.finditer(chunk):
            candidate = match.group(0).strip(" .,:;")
            if _is_date_like(candidate):
                continue
            digits = re.sub(r"\D", "", candidate)
            if 7 <= len(digits) <= 16:
                return re.sub(r"\s+", " ", candidate)
    return ""


def _is_date_like(value: str) -> bool:
    stripped = value.strip()
    if re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", stripped):
        return True
    return bool(re.fullmatch(r"(19|20)\d{2}", stripped))


def _infer_name_from_filename(filename: str) -> str:
    if not filename:
        return ""
    stem = Path(filename).stem
    stem = re.sub(r"^CV(?=[A-Z])", "", stem)
    stem = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stem)
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\([^)]*\)", " ", stem)
    raw_words = [part.strip() for part in stem.split() if part.strip()]
    drop = {
        "cv",
        "resume",
        "sap",
        "consultant",
        "conslutant",
        "developer",
        "updated",
        "update",
        "detail",
        "en",
        "eng",
        "ro",
        "v",
        "v1",
        "v2",
        "it",
    }
    words: list[str] = []
    for word in raw_words:
        cleaned = re.sub(r"[^A-Za-z]", "", word)
        if not cleaned or cleaned.lower() in drop:
            continue
        if re.fullmatch(r"\d+", word) or re.fullmatch(r"\d{6,8}", word):
            continue
        words.append(cleaned)
    if not words:
        return ""
    if len(words) == 1 and words[0].isupper() and len(words[0]) <= 4:
        return ""
    if len(words) > 5:
        words = words[:5]
    return _title_name(words)


def _infer_role_from_filename(filename: str) -> str:
    stem = Path(filename or "").stem
    clean = re.sub(r"[_\-]+", " ", stem)
    role_words: list[str] = []
    for label in ("Architect", "Consultant", "Developer", "Analyst", "Manager", "Basis", "FICO", "ABAP"):
        if re.search(rf"\b{re.escape(label)}\b", clean, re.I):
            role_words.append(label)
    if not role_words:
        return ""
    return " ".join(_dedupe(role_words))


def _infer_name_from_linkedin(linkedin: str) -> str:
    if not linkedin:
        return ""
    match = re.search(r"/in/([^/?#]+)", linkedin, re.I)
    if not match:
        return ""
    slug = re.sub(r"\d.*$", "", match.group(1)).strip("-_")
    words = [part for part in re.split(r"[-_.]+", slug) if part and part.lower() not in {"in", "profile"}]
    if 2 <= len(words) <= 5:
        return _title_name(words)
    return ""


def _title_name(words: list[str]) -> str:
    titled: list[str] = []
    for word in words:
        lower = word.lower()
        if lower in NAME_PARTICLES:
            titled.append(lower)
        elif word.isupper() and len(word) <= 3:
            titled.append(word)
        else:
            titled.append(word[:1].upper() + word[1:].lower())
    return " ".join(titled).strip()
