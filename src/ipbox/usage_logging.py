"""Usage logging primitives for SAP IS-U Assistant IP Box evidence."""
from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


SEARCH_MODES = {"AI_ONLY", "INCIDENTS_ONLY", "COMBINED"}
SOURCES_USED = {"KNOWLEDGE_BASE", "INCIDENTS", "BOTH", "MANUAL_CONTEXT"}
OUTPUT_TYPES = {
    "TECHNICAL_ANALYSIS",
    "JIRA_RESPONSE",
    "EMAIL",
    "DEBUG_CHECKLIST",
    "DOCUMENTATION",
    "TRANSLATION",
    "OTHER",
}
YES_PARTIAL_NO = {"YES", "PARTIAL", "NO"}
YES_NO = {"YES", "NO"}


@dataclass
class UsageRecord:
    usage_id: str
    timestamp: str
    user: str
    active_client: str
    ticket_reference: str
    task_type: str
    sap_module: str
    sap_isu_process: str
    search_mode: str
    sources_used: str
    number_of_documents_retrieved: int = 0
    average_similarity_score: float | None = None
    contains_z_objects: bool = False
    namespace_applied: str = "STANDARD"
    output_type: str = "TECHNICAL_ANALYSIS"
    output_used: str = "NO"
    used_for_client_delivery: str = "NO"
    human_reviewed: str = "NO"
    verification_status: str = "NOT_RECORDED"
    software_features_used: str = ""
    retrieved_kb_item_ids: str = ""
    retrieved_incident_ids: str = ""
    output_reference: str = ""
    actual_time_minutes: int = 0
    estimated_time_without_tool_minutes: int = 0
    estimated_time_saved_minutes: int = 0
    usefulness_rating: int | None = None
    accuracy_score: float | None = None
    software_contribution_factor: float = 0.0
    query_hash: str = ""
    response_hash: str = ""
    invoice_reference: str = ""
    evidence_path: str = ""
    notes: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        extra = data.pop("extra") or {}
        data.update(extra)
        return data


def generate_usage_id(prefix: str = "USE") -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:10].upper()}"


def hash_text(text: str | None) -> str:
    normalized = (text or "").replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def create_usage_record(
    *,
    user: str,
    active_client: str,
    ticket_reference: str,
    task_type: str,
    sap_module: str,
    sap_isu_process: str,
    search_mode: str,
    sources_used: str,
    query_text: str = "",
    response_text: str = "",
    usage_id: str | None = None,
    timestamp: str | None = None,
    **fields,
) -> UsageRecord:
    record = UsageRecord(
        usage_id=usage_id or generate_usage_id(),
        timestamp=timestamp or utc_now_iso(),
        user=user,
        active_client=active_client,
        ticket_reference=ticket_reference,
        task_type=task_type,
        sap_module=sap_module,
        sap_isu_process=sap_isu_process,
        search_mode=search_mode,
        sources_used=sources_used,
        query_hash=fields.pop("query_hash", "") or hash_text(query_text),
        response_hash=fields.pop("response_hash", "") or hash_text(response_text),
        **fields,
    )
    validate_usage_record(record)
    return record


def validate_usage_record(record: UsageRecord) -> None:
    if not record.usage_id:
        raise ValueError("usage_id is required")
    if record.search_mode not in SEARCH_MODES:
        raise ValueError("Invalid search_mode")
    if record.sources_used not in SOURCES_USED:
        raise ValueError("Invalid sources_used")
    if record.output_type not in OUTPUT_TYPES:
        raise ValueError("Invalid output_type")
    if record.output_used not in YES_PARTIAL_NO:
        raise ValueError("Invalid output_used")
    if record.used_for_client_delivery not in YES_NO:
        raise ValueError("Invalid used_for_client_delivery")
    if record.human_reviewed not in YES_NO:
        raise ValueError("Invalid human_reviewed")
    if not 0 <= record.software_contribution_factor <= 1:
        raise ValueError("software_contribution_factor must be between 0 and 1")
    if record.actual_time_minutes < 0 or record.estimated_time_without_tool_minutes < 0:
        raise ValueError("time values cannot be negative")
    if record.estimated_time_saved_minutes < 0:
        raise ValueError("estimated_time_saved_minutes cannot be negative")


def usage_log_path(data_root: Path, month: str) -> Path:
    return Path(data_root) / "ip_box" / "usage_logs" / f"{month}.jsonl"


def save_usage_event(data_root: Path, record: UsageRecord | dict) -> Path:
    if isinstance(record, dict):
        record = UsageRecord(**record)
    validate_usage_record(record)
    month = record.timestamp[:7]
    path = usage_log_path(data_root, month)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_usage_events(data_root: Path, month: str | None = None) -> list[dict]:
    root = Path(data_root) / "ip_box" / "usage_logs"
    paths = [usage_log_path(data_root, month)] if month else sorted(root.glob("*.jsonl"))
    events: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    events.append(json.loads(line))
    return events


def export_usage_events_csv(events: Iterable[dict], output_path: Path) -> Path:
    rows = list(events)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else []
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return output_path
