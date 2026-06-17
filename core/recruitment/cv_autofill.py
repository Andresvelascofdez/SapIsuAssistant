"""Rule-based CV autofill helpers for candidate forms."""
from __future__ import annotations

import re


def autofill_from_text(text: str) -> dict[str, str | float]:
    content = text or ""
    data: dict[str, str | float] = {}

    email = _first_match(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", content)
    if email:
        data["email"] = email

    phone = _extract_phone(content)
    if phone:
        data["phone"] = phone

    linkedin = _first_match(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s,)]+", content, flags=re.I)
    if linkedin:
        data["linkedin"] = linkedin

    name = _infer_name(content)
    if name:
        data["full_name"] = name

    role = _infer_role(content)
    if role:
        data["main_role"] = role

    seniority = _infer_seniority(content)
    if seniority:
        data["seniority"] = seniority

    years = _infer_years_experience(content)
    if years:
        data["years_experience"] = years

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
    return [line.strip(" \t-|*") for line in text.splitlines() if line.strip()]


def _infer_name(text: str) -> str:
    skip = re.compile(r"(@|https?://|linkedin|resume|curriculum|cv\b|phone|email|rate|years?)", re.I)
    for line in _lines(text)[:12]:
        words = line.split()
        if skip.search(line) or any(char.isdigit() for char in line):
            continue
        if 2 <= len(words) <= 4 and all(re.search(r"[A-Za-z]", word) for word in words):
            return " ".join(word.strip(",") for word in words)
    return ""


def _infer_role(text: str) -> str:
    role_words = re.compile(
        r"\b(consultant|developer|architect|engineer|manager|analyst|specialist|administrator)\b",
        re.I,
    )
    skip = re.compile(r"(@|https?://|linkedin|phone|email)", re.I)
    for line in _lines(text)[:18]:
        if len(line) <= 90 and role_words.search(line) and not skip.search(line):
            return line
    return ""


def _infer_seniority(text: str) -> str:
    precedence = ("Lead", "Senior", "Mid", "Junior", "Architect", "Consultant", "Developer")
    for label in precedence:
        if re.search(rf"\b{re.escape(label)}\b", text, re.I):
            return label
    if re.search(r"\bmid[- ]level\b", text, re.I):
        return "Mid"
    return ""


def _infer_years_experience(text: str) -> str:
    patterns = (
        (r"\bover\s+(\d{1,2})\s*(?:years|yrs)\b", "over {value} years"),
        (r"\b(\d{1,2})\+\s*(?:years|yrs)\b", "{value}+ years"),
        (r"\b(\d{1,2})\s*(?:years|yrs)\s+(?:of\s+)?experience\b", "{value} years"),
        (r"\b(\d{1,2})\s*(?:years|yrs)\b", "{value} years"),
    )
    for pattern, template in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return template.format(value=match.group(1))
    return ""


def _infer_rates(text: str) -> dict[str, float]:
    data: dict[str, float] = {}
    number = r"(\d+(?:[.,]\d+)?)"
    currency = r"(?:EUR|USD|GBP|€|\$|£)?"
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
    if re.search(r"\bEUR\b|€|\beuro\b", text, re.I):
        return "EUR"
    if re.search(r"\bUSD\b|\$", text, re.I):
        return "USD"
    if re.search(r"\bGBP\b|£", text, re.I):
        return "GBP"
    return ""


def _extract_phone(text: str) -> str:
    candidates = re.findall(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,5}\d{2,4}", text)
    for candidate in candidates:
        digits = re.sub(r"\D", "", candidate)
        if 7 <= len(digits) <= 16:
            return candidate.strip(" .,:;")
    return ""
