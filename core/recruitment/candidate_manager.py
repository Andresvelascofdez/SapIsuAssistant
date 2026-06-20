"""SQLite-backed candidate storage for the Recruitment module."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORK_MODES = ("Remote", "Hybrid", "Onsite", "Any")
CURRENCIES = ("EUR", "USD", "GBP", "Other")

CANDIDATE_FIELDS = (
    "full_name",
    "email",
    "phone",
    "linkedin",
    "country",
    "city",
    "timezone",
    "main_role",
    "seniority",
    "skills",
    "sap_modules",
    "languages",
    "years_experience",
    "work_mode",
    "rate_hour",
    "rate_day",
    "currency",
    "notes",
    "cv_file_path",
    "cv_text",
)

TEXT_FIELDS = (
    "full_name",
    "email",
    "phone",
    "linkedin",
    "country",
    "city",
    "timezone",
    "main_role",
    "seniority",
    "skills",
    "sap_modules",
    "languages",
    "years_experience",
    "work_mode",
    "currency",
    "notes",
    "cv_file_path",
    "cv_text",
)

SEARCH_FIELDS = (
    "full_name",
    "email",
    "phone",
    "linkedin",
    "country",
    "city",
    "timezone",
    "main_role",
    "seniority",
    "skills",
    "sap_modules",
    "languages",
    "years_experience",
    "work_mode",
    "notes",
    "cv_text",
)


class CandidateValidationError(ValueError):
    """Raised when a candidate payload does not satisfy module validation."""


@dataclass(frozen=True)
class Candidate:
    id: int
    full_name: str
    email: str
    phone: str
    linkedin: str
    country: str
    city: str
    timezone: str
    main_role: str
    seniority: str
    skills: str
    sap_modules: str
    languages: str
    years_experience: str
    work_mode: str
    rate_hour: float | None
    rate_day: float | None
    currency: str
    notes: str
    cv_file_path: str
    cv_text: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "linkedin": self.linkedin,
            "country": self.country,
            "city": self.city,
            "timezone": self.timezone,
            "main_role": self.main_role,
            "seniority": self.seniority,
            "skills": self.skills,
            "sap_modules": self.sap_modules,
            "languages": self.languages,
            "years_experience": self.years_experience,
            "work_mode": self.work_mode,
            "rate_hour": self.rate_hour,
            "rate_day": self.rate_day,
            "currency": self.currency,
            "notes": self.notes,
            "cv_file_path": self.cv_file_path,
            "cv_text": self.cv_text,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class CandidateManager:
    """Manage candidates in data/recruitment/candidates.db."""

    def __init__(self, data_root: Path | str = Path("data")) -> None:
        self.data_root = Path(data_root)
        self.recruitment_dir = self.data_root / "recruitment"
        self.cvs_dir = self.recruitment_dir / "cvs"
        self.db_path = self.recruitment_dir / "candidates.db"
        self.recruitment_dir.mkdir(parents=True, exist_ok=True)
        self.cvs_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT,
                    email TEXT,
                    phone TEXT,
                    linkedin TEXT,
                    country TEXT,
                    city TEXT,
                    timezone TEXT,
                    main_role TEXT,
                    seniority TEXT,
                    skills TEXT,
                    sap_modules TEXT,
                    languages TEXT,
                    years_experience TEXT,
                    work_mode TEXT,
                    rate_hour REAL,
                    rate_day REAL,
                    currency TEXT,
                    notes TEXT,
                    cv_file_path TEXT,
                    cv_text TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_updated_at ON candidates(updated_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_full_name ON candidates(full_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_email ON candidates(email)")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _parse_optional_float(value: Any, field_name: str) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
            if not value:
                return None
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise CandidateValidationError(f"{field_name} must be numeric when provided.") from exc
        if parsed < 0:
            raise CandidateValidationError(f"{field_name} cannot be negative.")
        return parsed

    @staticmethod
    def _parse_max_rate(value: Any) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
            if not value:
                return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    def _clean_payload(self, payload: dict[str, Any], existing: Candidate | None = None) -> dict[str, Any]:
        base = existing.to_dict() if existing else {field: "" for field in CANDIDATE_FIELDS}
        cleaned: dict[str, Any] = {}
        for field in CANDIDATE_FIELDS:
            value = payload.get(field, base.get(field))
            if field in ("rate_hour", "rate_day"):
                cleaned[field] = self._parse_optional_float(value, field)
            elif field in TEXT_FIELDS:
                cleaned[field] = "" if value is None else str(value).strip()

        if not cleaned["full_name"]:
            raise CandidateValidationError("Full name is mandatory.")
        if not cleaned["email"] and not cleaned["phone"] and not cleaned["linkedin"]:
            raise CandidateValidationError("Email, phone or LinkedIn is mandatory.")

        if not cleaned["work_mode"]:
            cleaned["work_mode"] = "Any"
        if cleaned["work_mode"] not in WORK_MODES:
            raise CandidateValidationError("Work mode must be Remote, Hybrid, Onsite or Any.")

        if not cleaned["currency"]:
            cleaned["currency"] = "EUR"
        if cleaned["currency"] not in CURRENCIES:
            raise CandidateValidationError("Currency must be EUR, USD, GBP or Other.")

        return cleaned

    @staticmethod
    def _row_to_candidate(row: sqlite3.Row | None) -> Candidate | None:
        if row is None:
            return None
        data = dict(row)
        return Candidate(**data)

    def create_candidate(self, payload: dict[str, Any]) -> Candidate:
        cleaned = self._clean_payload(payload)
        now = self._now()
        fields = list(CANDIDATE_FIELDS) + ["created_at", "updated_at"]
        values = [cleaned[field] for field in CANDIDATE_FIELDS] + [now, now]
        placeholders = ", ".join("?" for _ in fields)
        with self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO candidates ({', '.join(fields)}) VALUES ({placeholders})",
                values,
            )
            candidate_id = cursor.lastrowid
        candidate = self.get_candidate(candidate_id)
        if candidate is None:
            raise RuntimeError("Candidate was not persisted.")
        return candidate

    def update_candidate(self, candidate_id: int, payload: dict[str, Any]) -> Candidate:
        existing = self.get_candidate(candidate_id)
        if existing is None:
            raise KeyError(f"Candidate {candidate_id} not found.")
        cleaned = self._clean_payload(payload, existing=existing)
        updated_at = self._now()
        assignments = ", ".join(f"{field} = ?" for field in CANDIDATE_FIELDS) + ", updated_at = ?"
        values = [cleaned[field] for field in CANDIDATE_FIELDS] + [updated_at, candidate_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE candidates SET {assignments} WHERE id = ?", values)
        updated = self.get_candidate(candidate_id)
        if updated is None:
            raise RuntimeError("Candidate disappeared during update.")
        return updated

    def delete_candidate(self, candidate_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
            return cursor.rowcount > 0

    def get_candidate(self, candidate_id: int) -> Candidate | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
        return self._row_to_candidate(row)

    def list_candidates(self, search: str | None = None, filters: dict[str, Any] | None = None) -> list[Candidate]:
        where: list[str] = []
        params: list[Any] = []
        search = (search or "").strip()
        if search:
            clauses = [f"LOWER(COALESCE({field}, '')) LIKE ?" for field in SEARCH_FIELDS]
            where.append("(" + " OR ".join(clauses) + ")")
            params.extend([f"%{search.lower()}%"] * len(clauses))

        filters = filters or {}
        self._append_cv_text_filter(where, params, filters.get("cv_text"))
        self._append_text_filter(where, params, "skills", filters.get("skill_text"))
        self._append_text_filter(where, params, "sap_modules", filters.get("sap_module_text"))
        self._append_text_filter(where, params, "languages", filters.get("language_text"))
        self._append_text_filter(where, params, "country", filters.get("country"))
        self._append_text_filter(where, params, "seniority", filters.get("seniority"))

        work_mode = (filters.get("work_mode") or "").strip()
        if work_mode:
            where.append("LOWER(COALESCE(work_mode, '')) = ?")
            params.append(work_mode.lower())

        max_hourly = self._parse_max_rate(filters.get("max_hourly_rate"))
        if max_hourly is not None:
            where.append("rate_hour IS NOT NULL AND rate_hour <= ?")
            params.append(max_hourly)

        max_daily = self._parse_max_rate(filters.get("max_daily_rate"))
        if max_daily is not None:
            where.append("rate_day IS NOT NULL AND rate_day <= ?")
            params.append(max_daily)

        sql = "SELECT * FROM candidates"
        if where:
            sql += " WHERE " + " AND ".join(f"({clause})" for clause in where)
        sql += " ORDER BY updated_at DESC, id DESC"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [candidate for row in rows if (candidate := self._row_to_candidate(row)) is not None]

    def search_candidates(self, query: str, filters: dict[str, Any] | None = None) -> list[Candidate]:
        return self.list_candidates(search=query, filters=filters)

    @staticmethod
    def _append_text_filter(where: list[str], params: list[Any], field: str, value: Any) -> None:
        text = (value or "").strip()
        if text:
            where.append(f"LOWER(COALESCE({field}, '')) LIKE ?")
            params.append(f"%{text.lower()}%")

    @staticmethod
    def _append_cv_text_filter(where: list[str], params: list[Any], value: Any) -> None:
        text = (value or "").strip()
        if not text:
            return
        terms = [term for term in text.lower().split() if term]
        if not terms:
            return
        clauses = ["LOWER(COALESCE(cv_text, '')) LIKE ?" for _ in terms]
        where.append("(" + " AND ".join(clauses) + ")")
        params.extend(f"%{term}%" for term in terms)
