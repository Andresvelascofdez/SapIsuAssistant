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

from src.shared.version import APP_VERSION


SEARCH_MODES = {"AI_ONLY", "INCIDENTS_ONLY", "COMBINED"}
SOURCES_USED = {"KNOWLEDGE_BASE", "INCIDENTS", "BOTH", "MANUAL_CONTEXT"}
MANUAL_VERIFICATION_STATUSES = {"TODO/TBC", "reviewed", "used", "discarded"}
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
    product_version: str
    user: str
    active_client: str
    selected_scope: str
    selected_mode: str
    ticket_reference: str
    task_type: str
    sap_module: str
    sap_isu_process: str
    sap_process: str
    search_mode: str
    sources_used: str
    number_of_documents_retrieved: int = 0
    retrieval_count: int = 0
    average_similarity_score: float | None = None
    contains_z_objects: bool = False
    z_custom_objects_involved: bool = False
    namespace_applied: str = "STANDARD"
    standard_kb_used: str = "NO"
    client_kb_used: str = "NO"
    output_type: str = "TECHNICAL_ANALYSIS"
    output_used: str = "NO"
    used_for_client_delivery: str = "NO"
    delivery_used: str = "NO"
    human_reviewed: str = "NO"
    verification_status: str = "NOT_RECORDED"
    manual_verification_status: str = "TODO/TBC"
    excluded_from_ip_evidence: str = "NO"
    software_features_used: str = ""
    software_feature_used: str = ""
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
    selected_scope = fields.pop("selected_scope", fields.pop("scope", ""))
    selected_mode = fields.pop("selected_mode", search_mode)
    sap_process = fields.pop("sap_process", sap_isu_process)
    retrieval_count = int(fields.pop("retrieval_count", fields.get("number_of_documents_retrieved", 0)) or 0)
    number_retrieved = int(fields.pop("number_of_documents_retrieved", retrieval_count) or 0)
    contains_z = bool(fields.pop("contains_z_objects", False) or fields.get("z_custom_objects_involved", False))
    z_custom = bool(fields.pop("z_custom_objects_involved", contains_z))
    delivery_used = fields.pop("delivery_used", fields.get("used_for_client_delivery", "NO"))
    used_for_delivery = fields.pop("used_for_client_delivery", delivery_used)
    software_feature = fields.pop("software_feature_used", fields.get("software_features_used", ""))
    software_features = fields.pop("software_features_used", software_feature)
    record = UsageRecord(
        usage_id=usage_id or generate_usage_id(),
        timestamp=timestamp or utc_now_iso(),
        product_version=fields.pop("product_version", APP_VERSION),
        user=user,
        active_client=active_client,
        selected_scope=selected_scope,
        selected_mode=selected_mode,
        ticket_reference=ticket_reference,
        task_type=task_type,
        sap_module=sap_module,
        sap_isu_process=sap_isu_process,
        sap_process=sap_process,
        search_mode=search_mode,
        sources_used=sources_used,
        number_of_documents_retrieved=number_retrieved,
        retrieval_count=retrieval_count,
        contains_z_objects=contains_z,
        z_custom_objects_involved=z_custom,
        standard_kb_used=fields.pop("standard_kb_used", "NO"),
        client_kb_used=fields.pop("client_kb_used", "NO"),
        used_for_client_delivery=used_for_delivery,
        delivery_used=delivery_used,
        manual_verification_status=fields.pop("manual_verification_status", "TODO/TBC"),
        excluded_from_ip_evidence=fields.pop("excluded_from_ip_evidence", "NO"),
        software_features_used=software_features,
        software_feature_used=software_feature,
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
    if record.delivery_used not in YES_NO:
        raise ValueError("Invalid delivery_used")
    if record.human_reviewed not in YES_NO:
        raise ValueError("Invalid human_reviewed")
    if record.standard_kb_used not in YES_NO:
        raise ValueError("Invalid standard_kb_used")
    if record.client_kb_used not in YES_NO:
        raise ValueError("Invalid client_kb_used")
    if record.excluded_from_ip_evidence not in YES_NO:
        raise ValueError("Invalid excluded_from_ip_evidence")
    if record.manual_verification_status not in MANUAL_VERIFICATION_STATUSES:
        raise ValueError("Invalid manual_verification_status")
    if not 0 <= record.software_contribution_factor <= 1:
        raise ValueError("software_contribution_factor must be between 0 and 1")
    if record.actual_time_minutes < 0 or record.estimated_time_without_tool_minutes < 0:
        raise ValueError("time values cannot be negative")
    if record.estimated_time_saved_minutes < 0:
        raise ValueError("estimated_time_saved_minutes cannot be negative")
    if record.retrieval_count < 0 or record.number_of_documents_retrieved < 0:
        raise ValueError("retrieval counts cannot be negative")


def usage_log_path(data_root: Path, month: str) -> Path:
    return Path(data_root) / "ip_box" / "usage_logs" / f"{month}.jsonl"


def save_usage_event(data_root: Path, record: UsageRecord | dict) -> Path:
    if isinstance(record, dict):
        record = _record_from_dict(record)
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


def list_usage_events(
    data_root: Path,
    *,
    month: str | None = None,
    client: str | None = None,
    sap_module: str | None = None,
    sap_process: str | None = None,
    output_used: str | None = None,
    delivery_used: str | None = None,
    include_excluded: bool = True,
) -> list[dict]:
    """Read usage events and apply lightweight evidence-review filters."""
    events = read_usage_events(data_root, month)
    filtered: list[dict] = []
    for event in events:
        if client and str(event.get("active_client") or "").upper() != client.upper():
            continue
        if sap_module and str(event.get("sap_module") or "").lower() != sap_module.lower():
            continue
        event_process = event.get("sap_process") or event.get("sap_isu_process")
        if sap_process and str(event_process or "").lower() != sap_process.lower():
            continue
        if output_used and event.get("output_used") != output_used:
            continue
        if delivery_used and (event.get("delivery_used") or event.get("used_for_client_delivery")) != delivery_used:
            continue
        if not include_excluded and event.get("excluded_from_ip_evidence") == "YES":
            continue
        filtered.append(event)
    return filtered


def update_usage_event(data_root: Path, usage_id: str, updates: dict) -> dict | None:
    """Update review metadata for a recorded event by rewriting its month JSONL file."""
    allowed = {
        "ticket_reference",
        "sap_module",
        "sap_process",
        "sap_isu_process",
        "output_used",
        "used_for_client_delivery",
        "delivery_used",
        "human_reviewed",
        "verification_status",
        "manual_verification_status",
        "actual_time_minutes",
        "estimated_time_without_tool_minutes",
        "estimated_time_saved_minutes",
        "software_contribution_factor",
        "usefulness_rating",
        "accuracy_score",
        "output_reference",
        "invoice_reference",
        "evidence_path",
        "notes",
        "excluded_from_ip_evidence",
    }
    root = Path(data_root) / "ip_box" / "usage_logs"
    if not root.exists():
        return None
    for path in sorted(root.glob("*.jsonl")):
        rows = []
        found = None
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("usage_id") == usage_id:
                    for key, value in updates.items():
                        if key in allowed:
                            event[key] = _normalize_update_value(key, value)
                    if "sap_process" in updates and "sap_isu_process" not in updates:
                        event["sap_isu_process"] = updates["sap_process"]
                    if "used_for_client_delivery" in updates and "delivery_used" not in updates:
                        event["delivery_used"] = updates["used_for_client_delivery"]
                    if "delivery_used" in updates and "used_for_client_delivery" not in updates:
                        event["used_for_client_delivery"] = updates["delivery_used"]
                    found = event
                rows.append(event)
        if found:
            record = _record_from_dict(found)
            validate_usage_record(record)
            with path.open("w", encoding="utf-8", newline="\n") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            return found
    return None


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


def detect_custom_sap_objects(objects: Iterable[str] | None) -> bool:
    """Detect SAP customer namespace objects such as Z*, Y* and /NAMESPACE/*."""
    for obj in objects or []:
        value = str(obj or "").strip().upper()
        if not value:
            continue
        if value.startswith(("Z", "Y")):
            return True
        if value.startswith("/") and value.count("/") >= 2:
            return True
    return False


def make_id_list(values: Iterable[str | dict] | None) -> str:
    """Serialize IDs as a stable comma-separated evidence field."""
    ids: list[str] = []
    for value in values or []:
        if isinstance(value, dict):
            candidate = value.get("kb_id") or value.get("id") or value.get("incident_id")
        else:
            candidate = value
        if candidate:
            ids.append(str(candidate))
    return ",".join(ids)


def _record_from_dict(data: dict) -> UsageRecord:
    """Build a UsageRecord from persisted JSONL, preserving unknown audit fields."""
    defaults = _usage_defaults()
    known = set(defaults)
    payload = {**defaults, **{key: value for key, value in data.items() if key in known}}
    extra = dict(payload.get("extra") or {})
    extra.update({key: value for key, value in data.items() if key not in known})
    payload["extra"] = extra
    return UsageRecord(**payload)


def _normalize_update_value(key: str, value):
    if key in {
        "actual_time_minutes",
        "estimated_time_without_tool_minutes",
        "estimated_time_saved_minutes",
    }:
        return int(value or 0)
    if key in {"software_contribution_factor", "accuracy_score"}:
        return float(value or 0)
    if key == "usefulness_rating":
        return int(value) if value not in (None, "") else None
    return value


def _usage_defaults() -> dict:
    return {
        "usage_id": "",
        "timestamp": utc_now_iso(),
        "product_version": APP_VERSION,
        "user": "local-user",
        "active_client": "",
        "selected_scope": "",
        "selected_mode": "",
        "ticket_reference": "",
        "task_type": "OTHER",
        "sap_module": "",
        "sap_isu_process": "",
        "sap_process": "",
        "search_mode": "COMBINED",
        "sources_used": "MANUAL_CONTEXT",
        "number_of_documents_retrieved": 0,
        "retrieval_count": 0,
        "contains_z_objects": False,
        "z_custom_objects_involved": False,
        "namespace_applied": "STANDARD",
        "standard_kb_used": "NO",
        "client_kb_used": "NO",
        "output_type": "TECHNICAL_ANALYSIS",
        "output_used": "NO",
        "used_for_client_delivery": "NO",
        "delivery_used": "NO",
        "human_reviewed": "NO",
        "verification_status": "NOT_RECORDED",
        "manual_verification_status": "TODO/TBC",
        "excluded_from_ip_evidence": "NO",
        "software_features_used": "",
        "software_feature_used": "",
        "retrieved_kb_item_ids": "",
        "retrieved_incident_ids": "",
        "output_reference": "",
        "actual_time_minutes": 0,
        "estimated_time_without_tool_minutes": 0,
        "estimated_time_saved_minutes": 0,
        "usefulness_rating": None,
        "accuracy_score": None,
        "software_contribution_factor": 0.0,
        "query_hash": "",
        "response_hash": "",
        "invoice_reference": "",
        "evidence_path": "",
        "notes": "",
        "extra": {},
    }
