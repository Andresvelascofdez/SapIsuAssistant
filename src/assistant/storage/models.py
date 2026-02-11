"""
Knowledge base item model and enum types.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Optional


class KBItemType(str, Enum):
    """Fixed enum of knowledge types per PLAN.md section 7."""
    INCIDENT_PATTERN = "INCIDENT_PATTERN"
    ROOT_CAUSE = "ROOT_CAUSE"
    RESOLUTION = "RESOLUTION"
    VERIFICATION_STEPS = "VERIFICATION_STEPS"
    CUSTOMIZING = "CUSTOMIZING"
    ABAP_TECH_NOTE = "ABAP_TECH_NOTE"
    GLOSSARY = "GLOSSARY"
    RUNBOOK = "RUNBOOK"


class KBItemStatus(str, Enum):
    """KB item approval status."""
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class IngestionStatus(str, Enum):
    """Ingestion pipeline status."""
    DRAFT = "DRAFT"
    SYNTHESIZED = "SYNTHESIZED"
    FAILED = "FAILED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass
class KBItem:
    """Knowledge base item entity per PLAN.md section 5.1."""
    kb_id: str
    client_scope: str  # "standard" | "client"
    client_code: Optional[str]
    type: str
    title: str
    content_markdown: str
    tags_json: str
    sap_objects_json: str
    signals_json: str
    sources_json: str
    version: int
    status: str
    content_hash: str
    created_at: str
    updated_at: str


@dataclass
class Ingestion:
    """Ingestion record per PLAN.md section 5.1."""
    ingestion_id: str
    client_scope: str
    client_code: Optional[str]
    input_kind: str  # "text" | "pdf" | "docx"
    input_hash: str
    input_name: Optional[str]
    status: str
    model_used: str
    reasoning_effort: str
    created_at: str
    updated_at: str


class ChatScope(str, Enum):
    """Chat retrieval scope."""
    GENERAL = "general"
    CLIENT = "client"
    CLIENT_PLUS_STANDARD = "client_plus_standard"


@dataclass
class ChatSession:
    """Chat session entity for history persistence."""
    session_id: str
    scope: str  # general | client | client_plus_standard
    client_code: Optional[str]
    title: str
    is_pinned: int  # 0/1
    created_at: str
    updated_at: str
    last_message_at: str


@dataclass
class ChatMessage:
    """Chat message entity for history persistence."""
    message_id: str
    session_id: str
    role: str  # user | assistant
    content: str
    created_at: str
    used_kb_items_json: str  # JSON list of kb_ids/titles used
    model_called: int  # 0/1
