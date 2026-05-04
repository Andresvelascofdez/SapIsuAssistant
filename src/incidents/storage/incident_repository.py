"""SQLite repository for SAP IS-U incident evidence."""
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional


INCIDENT_STATUSES = {"OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"}
INCIDENT_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
IPBOX_RELEVANCE = {"UNCLEAR", "QUALIFYING_CANDIDATE", "NOT_QUALIFYING"}
EVIDENCE_KINDS = {"FILE", "LINK", "NOTE"}


@dataclass
class Incident:
    """SAP IS-U technical incident with IP Box evidence fields."""

    id: str
    incident_code: str
    client_code: str
    title: str
    status: str
    priority: str
    period_year: int
    period_month: int
    hours_spent: float
    sap_module: str | None
    sap_process: str | None
    sap_objects_json: str
    affected_ids_json: str
    problem_statement: str | None
    technical_uncertainty: str | None
    investigation: str | None
    solution: str | None
    implementation_notes: str | None
    verification: str | None
    outcome: str | None
    reusable_knowledge: str | None
    ipbox_relevance: str
    linked_kb_ids_json: str
    created_at: str
    updated_at: str


@dataclass
class IncidentEvidence:
    """Evidence item linked to an incident."""

    id: str
    incident_id: str
    title: str
    kind: str
    storage_path: str | None
    url: str | None
    sha256: str | None
    original_file_name: str | None
    mime_type: str | None
    size_bytes: int | None
    notes: str | None
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json_list(value: list[str] | str | None) -> str:
    if value is None:
        return "[]"
    if isinstance(value, str):
        items = [v.strip() for v in value.split(",") if v.strip()]
        return json.dumps(items)
    return json.dumps([str(v).strip() for v in value if str(v).strip()])


def _normalize_status(value: str | None, allowed: set[str], default: str) -> str:
    normalized = (value or default).strip().upper()
    if normalized not in allowed:
        raise ValueError(f"Invalid value: {normalized}")
    return normalized


def compute_sha256(file_bytes: bytes) -> str:
    """Compute a SHA256 hash for uploaded evidence."""
    return hashlib.sha256(file_bytes).hexdigest()


class IncidentRepository:
    """Repository for client-isolated incident evidence data."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    incident_code TEXT NOT NULL UNIQUE,
                    client_code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    period_year INTEGER NOT NULL,
                    period_month INTEGER NOT NULL,
                    hours_spent REAL NOT NULL DEFAULT 0.0,
                    sap_module TEXT,
                    sap_process TEXT,
                    sap_objects_json TEXT NOT NULL DEFAULT '[]',
                    affected_ids_json TEXT NOT NULL DEFAULT '[]',
                    problem_statement TEXT,
                    technical_uncertainty TEXT,
                    investigation TEXT,
                    solution TEXT,
                    implementation_notes TEXT,
                    verification TEXT,
                    outcome TEXT,
                    reusable_knowledge TEXT,
                    ipbox_relevance TEXT NOT NULL,
                    linked_kb_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incident_evidence (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    storage_path TEXT,
                    url TEXT,
                    sha256 TEXT,
                    original_file_name TEXT,
                    mime_type TEXT,
                    size_bytes INTEGER,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incidents_period ON incidents(period_year, period_month)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incidents_ipbox ON incidents(ipbox_relevance)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_evidence_incident ON incident_evidence(incident_id)"
            )
            conn.commit()

    def _next_incident_code(self, conn: sqlite3.Connection, year: int) -> str:
        prefix = f"INC-{year}-"
        rows = conn.execute(
            "SELECT incident_code FROM incidents WHERE incident_code LIKE ? ORDER BY incident_code DESC",
            (prefix + "%",),
        ).fetchall()
        max_seq = 0
        for (code,) in rows:
            try:
                max_seq = max(max_seq, int(code.rsplit("-", 1)[1]))
            except (ValueError, IndexError):
                continue
        return f"{prefix}{max_seq + 1:04d}"

    def create_incident(
        self,
        client_code: str,
        title: str,
        period_year: int | None = None,
        period_month: int | None = None,
        status: str = "OPEN",
        priority: str = "MEDIUM",
        hours_spent: float = 0.0,
        sap_module: str | None = None,
        sap_process: str | None = None,
        sap_objects: list[str] | str | None = None,
        affected_ids: list[str] | str | None = None,
        problem_statement: str | None = None,
        technical_uncertainty: str | None = None,
        investigation: str | None = None,
        solution: str | None = None,
        implementation_notes: str | None = None,
        verification: str | None = None,
        outcome: str | None = None,
        reusable_knowledge: str | None = None,
        ipbox_relevance: str = "UNCLEAR",
    ) -> Incident:
        title = title.strip()
        client_code = client_code.strip().upper()
        if not title:
            raise ValueError("Title is required.")
        if not client_code:
            raise ValueError("client_code is required.")
        now_dt = datetime.now(UTC)
        year = now_dt.year if period_year is None else int(period_year)
        month = now_dt.month if period_month is None else int(period_month)
        if not 1 <= int(month) <= 12:
            raise ValueError("period_month must be between 1 and 12.")
        if float(hours_spent or 0.0) < 0:
            raise ValueError("hours_spent cannot be negative.")
        status = _normalize_status(status, INCIDENT_STATUSES, "OPEN")
        priority = _normalize_status(priority, INCIDENT_PRIORITIES, "MEDIUM")
        ipbox_relevance = _normalize_status(ipbox_relevance, IPBOX_RELEVANCE, "UNCLEAR")
        incident_id = str(uuid.uuid4())
        timestamp = _now()

        with self._conn() as conn:
            incident_code = self._next_incident_code(conn, int(year))
            conn.execute(
                """
                INSERT INTO incidents (
                    id, incident_code, client_code, title, status, priority,
                    period_year, period_month, hours_spent, sap_module, sap_process,
                    sap_objects_json, affected_ids_json, problem_statement,
                    technical_uncertainty, investigation, solution, implementation_notes,
                    verification, outcome, reusable_knowledge, ipbox_relevance,
                    linked_kb_ids_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)
                """,
                (
                    incident_id,
                    incident_code,
                    client_code,
                    title,
                    status,
                    priority,
                    year,
                    month,
                    float(hours_spent or 0.0),
                    sap_module,
                    sap_process,
                    _json_list(sap_objects),
                    _json_list(affected_ids),
                    problem_statement,
                    technical_uncertainty,
                    investigation,
                    solution,
                    implementation_notes,
                    verification,
                    outcome,
                    reusable_knowledge,
                    ipbox_relevance,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        created = self.get_incident(incident_id)
        if not created:
            raise RuntimeError("Incident was not created.")
        return created

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, incident_code, client_code, title, status, priority,
                       period_year, period_month, hours_spent, sap_module, sap_process,
                       sap_objects_json, affected_ids_json, problem_statement,
                       technical_uncertainty, investigation, solution, implementation_notes,
                       verification, outcome, reusable_knowledge, ipbox_relevance,
                       linked_kb_ids_json, created_at, updated_at
                FROM incidents WHERE id = ?
                """,
                (incident_id,),
            ).fetchone()
        return Incident(*row) if row else None

    def list_incidents(
        self,
        year: int | None = None,
        month: int | None = None,
        status: str | None = None,
        ipbox_relevance: str | None = None,
        search: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Incident]:
        clauses = []
        params: list = []
        if year is not None:
            clauses.append("period_year = ?")
            params.append(year)
        if month is not None:
            clauses.append("period_month = ?")
            params.append(month)
        if status:
            clauses.append("status = ?")
            params.append(status.strip().upper())
        if ipbox_relevance:
            clauses.append("ipbox_relevance = ?")
            params.append(ipbox_relevance.strip().upper())
        if search:
            clauses.append(
                "("
                "incident_code LIKE ? OR title LIKE ? OR sap_module LIKE ? OR sap_process LIKE ? OR "
                "sap_objects_json LIKE ? OR affected_ids_json LIKE ? OR problem_statement LIKE ? OR "
                "technical_uncertainty LIKE ? OR investigation LIKE ? OR solution LIKE ? OR "
                "verification LIKE ? OR outcome LIKE ? OR reusable_knowledge LIKE ?"
                ")"
            )
            like = f"%{search}%"
            params.extend([like] * 13)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = (
            "SELECT id, incident_code, client_code, title, status, priority, "
            "period_year, period_month, hours_spent, sap_module, sap_process, "
            "sap_objects_json, affected_ids_json, problem_statement, "
            "technical_uncertainty, investigation, solution, implementation_notes, "
            "verification, outcome, reusable_knowledge, ipbox_relevance, "
            "linked_kb_ids_json, created_at, updated_at FROM incidents"
            f"{where} ORDER BY period_year DESC, period_month DESC, updated_at DESC"
        )
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [Incident(*r) for r in rows]

    def update_incident(self, incident_id: str, **kwargs) -> Optional[Incident]:
        allowed = {
            "title",
            "status",
            "priority",
            "period_year",
            "period_month",
            "hours_spent",
            "sap_module",
            "sap_process",
            "problem_statement",
            "technical_uncertainty",
            "investigation",
            "solution",
            "implementation_notes",
            "verification",
            "outcome",
            "reusable_knowledge",
            "ipbox_relevance",
        }
        updates = []
        params = []
        for key, value in kwargs.items():
            if key in ("sap_objects", "affected_ids"):
                updates.append(f"{key}_json = ?")
                params.append(_json_list(value))
            elif key in allowed:
                if key == "status":
                    value = _normalize_status(value, INCIDENT_STATUSES, "OPEN")
                elif key == "priority":
                    value = _normalize_status(value, INCIDENT_PRIORITIES, "MEDIUM")
                elif key == "ipbox_relevance":
                    value = _normalize_status(value, IPBOX_RELEVANCE, "UNCLEAR")
                elif key == "period_month":
                    if not 1 <= int(value) <= 12:
                        raise ValueError("period_month must be between 1 and 12.")
                    value = int(value)
                elif key == "period_year":
                    value = int(value)
                elif key == "hours_spent":
                    value = float(value or 0.0)
                    if value < 0:
                        raise ValueError("hours_spent cannot be negative.")
                updates.append(f"{key} = ?")
                params.append(value)
        if not updates:
            return self.get_incident(incident_id)
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(incident_id)
        with self._conn() as conn:
            conn.execute(f"UPDATE incidents SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        return self.get_incident(incident_id)

    def delete_incident(self, incident_id: str) -> bool:
        with self._conn() as conn:
            deleted = conn.execute("DELETE FROM incidents WHERE id = ?", (incident_id,)).rowcount
            conn.commit()
        return deleted > 0

    def add_evidence(
        self,
        incident_id: str,
        title: str,
        kind: str,
        storage_path: str | None = None,
        url: str | None = None,
        sha256: str | None = None,
        original_file_name: str | None = None,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        notes: str | None = None,
    ) -> IncidentEvidence:
        if not self.get_incident(incident_id):
            raise ValueError("Incident not found.")
        title = title.strip()
        if not title:
            raise ValueError("Evidence title is required.")
        kind = _normalize_status(kind, EVIDENCE_KINDS, "FILE")
        if kind == "FILE" and not storage_path:
            raise ValueError("storage_path is required for file evidence.")
        if kind == "LINK" and not url:
            raise ValueError("url is required for link evidence.")
        evidence_id = str(uuid.uuid4())
        timestamp = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO incident_evidence (
                    id, incident_id, title, kind, storage_path, url, sha256,
                    original_file_name, mime_type, size_bytes, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    incident_id,
                    title,
                    kind,
                    storage_path,
                    url,
                    sha256,
                    original_file_name,
                    mime_type,
                    size_bytes,
                    notes,
                    timestamp,
                ),
            )
            conn.commit()
        evidence = self.get_evidence(evidence_id)
        if not evidence:
            raise RuntimeError("Evidence was not created.")
        return evidence

    def get_evidence(self, evidence_id: str) -> Optional[IncidentEvidence]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, incident_id, title, kind, storage_path, url, sha256,
                       original_file_name, mime_type, size_bytes, notes, created_at
                FROM incident_evidence WHERE id = ?
                """,
                (evidence_id,),
            ).fetchone()
        return IncidentEvidence(*row) if row else None

    def list_evidence(self, incident_id: str) -> list[IncidentEvidence]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, incident_id, title, kind, storage_path, url, sha256,
                       original_file_name, mime_type, size_bytes, notes, created_at
                FROM incident_evidence WHERE incident_id = ? ORDER BY created_at DESC
                """,
                (incident_id,),
            ).fetchall()
        return [IncidentEvidence(*r) for r in rows]

    def delete_evidence(self, evidence_id: str) -> Optional[IncidentEvidence]:
        evidence = self.get_evidence(evidence_id)
        if not evidence:
            return None
        with self._conn() as conn:
            conn.execute("DELETE FROM incident_evidence WHERE id = ?", (evidence_id,))
            conn.commit()
        return evidence

    def link_kb_draft(self, incident_id: str, kb_id: str) -> Optional[Incident]:
        incident = self.get_incident(incident_id)
        if not incident:
            return None
        linked = json.loads(incident.linked_kb_ids_json or "[]")
        if kb_id not in linked:
            linked.append(kb_id)
        return self.update_linked_kb_ids(incident_id, linked)

    def update_linked_kb_ids(self, incident_id: str, linked_kb_ids: list[str]) -> Optional[Incident]:
        with self._conn() as conn:
            conn.execute(
                "UPDATE incidents SET linked_kb_ids_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(linked_kb_ids), _now(), incident_id),
            )
            conn.commit()
        return self.get_incident(incident_id)

    def year_summary(self, year: int) -> dict:
        incidents = self.list_incidents(year=year)
        by_relevance: dict[str, int] = {}
        total_hours = 0.0
        for incident in incidents:
            by_relevance[incident.ipbox_relevance] = by_relevance.get(incident.ipbox_relevance, 0) + 1
            total_hours += incident.hours_spent
        return {
            "count": len(incidents),
            "total_hours": round(total_hours, 2),
            "by_relevance": by_relevance,
        }
