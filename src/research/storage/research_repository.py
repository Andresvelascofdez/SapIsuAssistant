"""SQLite repository for SAP IS-U research sources and KB candidates."""
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


SOURCE_TIERS = {"A", "B", "C", "D"}
SOURCE_KINDS = {
    "OFFICIAL",
    "LEARNING",
    "COMMUNITY",
    "TECH_DICTIONARY",
    "MARKET_RULES",
    "REGULATOR",
    "BOOK_REFERENCE",
    "BLOG",
}
USAGE_POLICIES = {"SUMMARY_OK", "REFERENCE_ONLY", "CONTEXT_ONLY"}
CANDIDATE_STATUSES = {"COLLECTED", "NORMALIZED", "AUDITED", "PROMOTED", "REJECTED"}
AUDIT_STATUSES = {"PENDING", "PASSED", "NEEDS_REVIEW", "REJECTED"}
COPYRIGHT_RISKS = {"LOW", "MEDIUM", "HIGH"}
RUN_STATUSES = {"QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"}
AGENT_STATUSES = {"PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED"}
EVENT_LEVELS = {"INFO", "WARNING", "ERROR", "SUCCESS"}
DISCOVERED_TOPIC_STATUSES = {"DISCOVERED", "QUEUED", "INGESTED", "REJECTED"}


@dataclass
class ResearchSource:
    id: str
    priority: int
    name: str
    kind: str
    tier: str
    base_url: str
    usage_policy: str
    enabled: int
    notes: str | None
    created_at: str
    updated_at: str


@dataclass
class KBCandidate:
    id: str
    source_id: str
    source_name: str
    client_scope: str
    client_code: str | None
    url: str | None
    title: str
    raw_excerpt: str
    kb_type: str
    content_markdown: str
    tags_json: str
    sap_objects_json: str
    signals_json: str
    sources_json: str
    confidence_score: float
    copyright_risk: str
    audit_status: str
    audit_notes: str | None
    status: str
    promoted_kb_id: str | None
    content_hash: str
    created_at: str
    updated_at: str


@dataclass
class ResearchRun:
    id: str
    topic: str
    client_scope: str
    client_code: str | None
    source_ids_json: str
    max_results_per_source: int
    auto_promote: int
    auto_index: int
    status: str
    collector_status: str
    normalizer_status: str
    auditor_status: str
    ingestor_status: str
    indexer_status: str
    discovered_count: int
    fetched_count: int
    candidate_count: int
    promoted_count: int
    indexed_count: int
    error: str | None
    created_at: str
    updated_at: str
    completed_at: str | None


@dataclass
class ResearchRunEvent:
    id: str
    run_id: str
    agent: str
    level: str
    message: str
    payload_json: str
    created_at: str


@dataclass
class CrawlRun:
    id: str
    client_scope: str
    client_code: str | None
    source_ids_json: str
    seed_queries_json: str
    max_pages_per_source: int
    max_topics: int
    auto_queue_runs: int
    auto_promote: int
    auto_index: int
    status: str
    scout_status: str
    crawler_status: str
    topic_status: str
    queue_status: str
    discovered_url_count: int
    fetched_page_count: int
    discovered_topic_count: int
    queued_run_count: int
    error: str | None
    created_at: str
    updated_at: str
    completed_at: str | None


@dataclass
class CrawlRunEvent:
    id: str
    crawl_id: str
    agent: str
    level: str
    message: str
    payload_json: str
    created_at: str


@dataclass
class DiscoveredTopic:
    id: str
    source_id: str
    source_name: str
    url: str | None
    title: str
    topic: str
    category: str | None
    objects_json: str
    tags_json: str
    confidence_score: float
    status: str
    queued_run_id: str | None
    content_hash: str
    first_seen_at: str
    updated_at: str


DEFAULT_SOURCES = [
    {
        "id": "sap-help",
        "priority": 1,
        "name": "SAP Help Portal",
        "kind": "OFFICIAL",
        "tier": "A",
        "base_url": "https://help.sap.com",
        "usage_policy": "SUMMARY_OK",
        "notes": "Primary reliable functional documentation for SAP IS-U and S/4HANA Utilities.",
    },
    {
        "id": "sap-learning",
        "priority": 2,
        "name": "SAP Learning",
        "kind": "LEARNING",
        "tier": "A",
        "base_url": "https://learning.sap.com",
        "usage_policy": "SUMMARY_OK",
        "notes": "Didactic process explanations for meter-to-cash, move-in/out, billing and analytics.",
    },
    {
        "id": "sap-community-utilities",
        "priority": 3,
        "name": "SAP Community Utilities",
        "kind": "COMMUNITY",
        "tier": "C",
        "base_url": "https://community.sap.com",
        "usage_policy": "CONTEXT_ONLY",
        "notes": "Practical context from consultants and community posts; not final technical authority.",
    },
    {
        "id": "sap-business-accelerator-hub",
        "priority": 4,
        "name": "SAP Business Accelerator Hub",
        "kind": "OFFICIAL",
        "tier": "A",
        "base_url": "https://api.sap.com",
        "usage_policy": "SUMMARY_OK",
        "notes": "APIs, integration packages and modern S/4HANA/BTP service metadata.",
    },
    {
        "id": "sap-datasheet",
        "priority": 5,
        "name": "SAP Datasheet",
        "kind": "TECH_DICTIONARY",
        "tier": "B",
        "base_url": "https://www.sapdatasheet.org",
        "usage_policy": "SUMMARY_OK",
        "notes": "Public technical object dictionary for tables, domains, function modules and messages.",
    },
    {
        "id": "leanx",
        "priority": 6,
        "name": "LeanX",
        "kind": "TECH_DICTIONARY",
        "tier": "B",
        "base_url": "https://leanx.eu",
        "usage_policy": "SUMMARY_OK",
        "notes": "Table and field sheets with keys and relationships.",
    },
    {
        "id": "tcodesearch",
        "priority": 7,
        "name": "TCodeSearch",
        "kind": "TECH_DICTIONARY",
        "tier": "B",
        "base_url": "https://www.tcodesearch.com",
        "usage_policy": "SUMMARY_OK",
        "notes": "Secondary source for transactions, tables, fields and related objects.",
    },
    {
        "id": "se80",
        "priority": 8,
        "name": "SE80.co.uk",
        "kind": "TECH_DICTIONARY",
        "tier": "B",
        "base_url": "https://www.se80.co.uk",
        "usage_policy": "SUMMARY_OK",
        "notes": "Complementary ABAP object, table, class, function and report reference.",
    },
    {
        "id": "michael-management-messages",
        "priority": 9,
        "name": "Michael Management SAP Error Messages",
        "kind": "TECH_DICTIONARY",
        "tier": "B",
        "base_url": "https://www.michaelmanagement.com",
        "usage_policy": "SUMMARY_OK",
        "notes": "SAP error message lookup by class, number or keyword; validate important entries.",
    },
    {
        "id": "bdew-edi-energy",
        "priority": 10,
        "name": "Bundesnetzagentur / BDEW / EDI@Energy",
        "kind": "MARKET_RULES",
        "tier": "A",
        "base_url": "https://www.edi-energy.de",
        "usage_policy": "SUMMARY_OK",
        "notes": "German MaKo, UTILMD, MSCONS, APERAK, GPKE, WiM, MaBiS and EDIFACT rules.",
    },
    {
        "id": "cnmc-spain",
        "priority": 11,
        "name": "CNMC Spain Energy Data Exchange",
        "kind": "REGULATOR",
        "tier": "A",
        "base_url": "https://www.cnmc.es",
        "usage_policy": "SUMMARY_OK",
        "notes": "Spanish electricity and gas distributor/retailer data exchange formats and market process references.",
    },
    {
        "id": "uregni-retail",
        "priority": 12,
        "name": "Utility Regulator Northern Ireland Retail Market",
        "kind": "REGULATOR",
        "tier": "A",
        "base_url": "https://www.uregni.gov.uk",
        "usage_policy": "SUMMARY_OK",
        "notes": "Northern Ireland retail market procedures and market message implementation guides.",
    },
    {
        "id": "ireland-rmd",
        "priority": 13,
        "name": "Ireland Retail Market Design Service",
        "kind": "REGULATOR",
        "tier": "A",
        "base_url": "https://rmdservice.com",
        "usage_policy": "SUMMARY_OK",
        "notes": "Irish retail electricity market procedures and XML market message catalogue.",
    },
    {
        "id": "cre-france",
        "priority": 14,
        "name": "CRE France Retail Energy Market",
        "kind": "REGULATOR",
        "tier": "A",
        "base_url": "https://www.cre.fr",
        "usage_policy": "SUMMARY_OK",
        "notes": "French retail electricity and gas market procedures and GTE/GTG context.",
    },
    {
        "id": "sap-press-rheinwerk",
        "priority": 21,
        "name": "SAP PRESS / Rheinwerk",
        "kind": "BOOK_REFERENCE",
        "tier": "D",
        "base_url": "https://www.sap-press.com",
        "usage_policy": "REFERENCE_ONLY",
        "notes": "Manual reference only. Do not scrape or store book content.",
    },
    {
        "id": "consulting-blogs",
        "priority": 22,
        "name": "Specialized Consulting Blogs",
        "kind": "BLOG",
        "tier": "C",
        "base_url": "",
        "usage_policy": "CONTEXT_ONLY",
        "notes": "Convista, Natuvion, Arvato, Gambit and similar sources for general context.",
    },
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json_list(value: list[str] | str | None) -> str:
    if value is None:
        return "[]"
    if isinstance(value, str):
        return json.dumps([v.strip() for v in value.split(",") if v.strip()])
    return json.dumps([str(v).strip() for v in value if str(v).strip()])


def _json_obj(value: dict | None) -> str:
    return json.dumps(value or {})


def _hash_candidate(source_id: str, url: str | None, title: str, content_markdown: str) -> str:
    payload = f"{source_id}|{url or ''}|{title}|{content_markdown}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hash_topic(topic: str) -> str:
    return hashlib.sha256(" ".join((topic or "").lower().split()).encode("utf-8")).hexdigest()


class ResearchRepository:
    """Repository for source registry and pre-KB research candidates."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_sources (
                    id TEXT PRIMARY KEY,
                    priority INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    base_url TEXT,
                    usage_policy TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_candidates (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    client_scope TEXT NOT NULL,
                    client_code TEXT,
                    url TEXT,
                    title TEXT NOT NULL,
                    raw_excerpt TEXT NOT NULL,
                    kb_type TEXT NOT NULL,
                    content_markdown TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    sap_objects_json TEXT NOT NULL,
                    signals_json TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    copyright_risk TEXT NOT NULL,
                    audit_status TEXT NOT NULL,
                    audit_notes TEXT,
                    status TEXT NOT NULL,
                    promoted_kb_id TEXT,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES research_sources(id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kb_candidates_status ON kb_candidates(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kb_candidates_scope ON kb_candidates(client_scope, client_code)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_kb_candidates_hash ON kb_candidates(content_hash)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_runs (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    client_scope TEXT NOT NULL,
                    client_code TEXT,
                    source_ids_json TEXT NOT NULL,
                    max_results_per_source INTEGER NOT NULL,
                    auto_promote INTEGER NOT NULL,
                    auto_index INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    collector_status TEXT NOT NULL,
                    normalizer_status TEXT NOT NULL,
                    auditor_status TEXT NOT NULL,
                    ingestor_status TEXT NOT NULL,
                    indexer_status TEXT NOT NULL DEFAULT 'PENDING',
                    discovered_count INTEGER NOT NULL DEFAULT 0,
                    fetched_count INTEGER NOT NULL DEFAULT 0,
                    candidate_count INTEGER NOT NULL DEFAULT 0,
                    promoted_count INTEGER NOT NULL DEFAULT 0,
                    indexed_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            self._ensure_column(conn, "research_runs", "auto_index", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "research_runs", "indexer_status", "TEXT NOT NULL DEFAULT 'PENDING'")
            self._ensure_column(conn, "research_runs", "indexed_count", "INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_run_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_runs_status ON research_runs(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_run_events_run ON research_run_events(run_id, created_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_runs (
                    id TEXT PRIMARY KEY,
                    client_scope TEXT NOT NULL,
                    client_code TEXT,
                    source_ids_json TEXT NOT NULL,
                    seed_queries_json TEXT NOT NULL,
                    max_pages_per_source INTEGER NOT NULL,
                    max_topics INTEGER NOT NULL,
                    auto_queue_runs INTEGER NOT NULL,
                    auto_promote INTEGER NOT NULL,
                    auto_index INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    scout_status TEXT NOT NULL,
                    crawler_status TEXT NOT NULL,
                    topic_status TEXT NOT NULL,
                    queue_status TEXT NOT NULL,
                    discovered_url_count INTEGER NOT NULL DEFAULT 0,
                    fetched_page_count INTEGER NOT NULL DEFAULT 0,
                    discovered_topic_count INTEGER NOT NULL DEFAULT 0,
                    queued_run_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS crawl_run_events (
                    id TEXT PRIMARY KEY,
                    crawl_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (crawl_id) REFERENCES crawl_runs(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discovered_topics (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    url TEXT,
                    title TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    category TEXT,
                    objects_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    status TEXT NOT NULL,
                    queued_run_id TEXT,
                    content_hash TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_crawl_runs_status ON crawl_runs(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_crawl_events_run ON crawl_run_events(crawl_id, created_at)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_discovered_topics_hash ON discovered_topics(content_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_discovered_topics_status ON discovered_topics(status)"
            )

    def seed_default_sources(self) -> int:
        inserted = 0
        with self._conn() as conn:
            for source in DEFAULT_SOURCES:
                now = _now()
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO research_sources (
                        id, priority, name, kind, tier, base_url, usage_policy,
                        enabled, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        source["id"],
                        source["priority"],
                        source["name"],
                        source["kind"],
                        source["tier"],
                        source["base_url"],
                        source["usage_policy"],
                        source["notes"],
                        now,
                        now,
                    ),
                )
                inserted += cur.rowcount
        return inserted

    def list_sources(self, enabled_only: bool = False) -> list[ResearchSource]:
        self.seed_default_sources()
        query = (
            "SELECT id, priority, name, kind, tier, base_url, usage_policy, enabled, notes, created_at, updated_at "
            "FROM research_sources"
        )
        params: list[object] = []
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY priority ASC, name ASC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._source_from_row(row) for row in rows]

    def get_source(self, source_id: str) -> ResearchSource | None:
        self.seed_default_sources()
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, priority, name, kind, tier, base_url, usage_policy, enabled, notes, created_at, updated_at
                FROM research_sources WHERE id = ?
                """,
                (source_id,),
            ).fetchone()
        return self._source_from_row(row) if row else None

    def create_candidate(
        self,
        *,
        source: ResearchSource,
        client_scope: str,
        client_code: str | None,
        url: str | None,
        title: str,
        raw_excerpt: str,
        kb_type: str,
        content_markdown: str,
        tags: list[str],
        sap_objects: list[str],
        signals: dict,
        sources: dict,
        confidence_score: float,
        copyright_risk: str,
        audit_status: str,
        audit_notes: str | None,
        status: str = "AUDITED",
    ) -> tuple[KBCandidate, bool]:
        if client_scope not in {"standard", "client"}:
            raise ValueError("client_scope must be standard or client")
        if client_scope == "client" and not client_code:
            raise ValueError("client_code is required for client scope")
        if copyright_risk not in COPYRIGHT_RISKS:
            raise ValueError("Invalid copyright_risk")
        if audit_status not in AUDIT_STATUSES:
            raise ValueError("Invalid audit_status")
        if status not in CANDIDATE_STATUSES:
            raise ValueError("Invalid candidate status")
        title = (title or "").strip()
        raw_excerpt = (raw_excerpt or "").strip()
        content_markdown = (content_markdown or "").strip()
        if not title:
            raise ValueError("title is required")
        if not raw_excerpt:
            raise ValueError("raw_excerpt is required")
        if not content_markdown:
            raise ValueError("content_markdown is required")

        content_hash = _hash_candidate(source.id, url, title, content_markdown)
        now = _now()
        candidate_id = str(uuid.uuid4())

        with self._conn() as conn:
            existing = conn.execute(
                """
                SELECT id FROM kb_candidates WHERE content_hash = ?
                """,
                (content_hash,),
            ).fetchone()
            if existing:
                candidate = self.get_candidate(existing[0])
                return candidate, False

            conn.execute(
                """
                INSERT INTO kb_candidates (
                    id, source_id, source_name, client_scope, client_code, url,
                    title, raw_excerpt, kb_type, content_markdown, tags_json,
                    sap_objects_json, signals_json, sources_json, confidence_score,
                    copyright_risk, audit_status, audit_notes, status, promoted_kb_id,
                    content_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    candidate_id,
                    source.id,
                    source.name,
                    client_scope,
                    client_code,
                    url,
                    title,
                    raw_excerpt,
                    kb_type,
                    content_markdown,
                    _json_list(tags),
                    _json_list(sap_objects),
                    _json_obj(signals),
                    _json_obj(sources),
                    float(confidence_score),
                    copyright_risk,
                    audit_status,
                    audit_notes,
                    status,
                    content_hash,
                    now,
                    now,
                ),
            )

        return self.get_candidate(candidate_id), True

    def list_candidates(
        self,
        *,
        client_scope: str | None = None,
        client_code: str | None = None,
        status: str | None = None,
        audit_status: str | None = None,
        limit: int = 100,
    ) -> list[KBCandidate]:
        clauses = []
        params: list[object] = []
        if client_scope:
            clauses.append("client_scope = ?")
            params.append(client_scope)
        if client_scope == "client" and client_code:
            clauses.append("client_code = ?")
            params.append(client_code)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if audit_status:
            clauses.append("audit_status = ?")
            params.append(audit_status)
        query = self._candidate_select()
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    def get_candidate(self, candidate_id: str) -> KBCandidate | None:
        with self._conn() as conn:
            row = conn.execute(
                self._candidate_select() + " WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return self._candidate_from_row(row) if row else None

    def update_candidate_status(
        self,
        candidate_id: str,
        *,
        status: str,
        promoted_kb_id: str | None = None,
        audit_status: str | None = None,
        audit_notes: str | None = None,
    ) -> KBCandidate | None:
        if status not in CANDIDATE_STATUSES:
            raise ValueError("Invalid candidate status")
        updates = ["status = ?", "updated_at = ?"]
        params: list[object] = [status, _now()]
        if promoted_kb_id is not None:
            updates.append("promoted_kb_id = ?")
            params.append(promoted_kb_id)
        if audit_status is not None:
            if audit_status not in AUDIT_STATUSES:
                raise ValueError("Invalid audit_status")
            updates.append("audit_status = ?")
            params.append(audit_status)
        if audit_notes is not None:
            updates.append("audit_notes = ?")
            params.append(audit_notes)
        params.append(candidate_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE kb_candidates SET {', '.join(updates)} WHERE id = ?",
                params,
            )
        return self.get_candidate(candidate_id)

    def create_run(
        self,
        *,
        topic: str,
        client_scope: str,
        client_code: str | None,
        source_ids: list[str],
        max_results_per_source: int = 2,
        auto_promote: bool = True,
        auto_index: bool = False,
    ) -> ResearchRun:
        if client_scope not in {"standard", "client"}:
            raise ValueError("client_scope must be standard or client")
        if client_scope == "client" and not client_code:
            raise ValueError("client_code is required for client scope")
        topic = (topic or "").strip()
        if not topic:
            raise ValueError("topic is required")
        source_ids = [s.strip() for s in source_ids if s and s.strip()]
        if not source_ids:
            raise ValueError("At least one source is required")

        run_id = str(uuid.uuid4())
        now = _now()
        auto_index = bool(auto_promote and auto_index)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO research_runs (
                    id, topic, client_scope, client_code, source_ids_json,
                    max_results_per_source, auto_promote, auto_index, status,
                    collector_status, normalizer_status, auditor_status, ingestor_status, indexer_status,
                    discovered_count, fetched_count, candidate_count, promoted_count, indexed_count,
                    error, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', 'PENDING', 'PENDING', 'PENDING', 'PENDING', 'PENDING', 0, 0, 0, 0, 0, NULL, ?, ?, NULL)
                """,
                (
                    run_id,
                    topic,
                    client_scope,
                    client_code,
                    json.dumps(source_ids),
                    max(1, min(int(max_results_per_source), 10)),
                    1 if auto_promote else 0,
                    1 if auto_index else 0,
                    now,
                    now,
                ),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> ResearchRun | None:
        with self._conn() as conn:
            row = conn.execute(
                self._run_select() + " WHERE id = ?",
                (run_id,),
            ).fetchone()
        return self._run_from_row(row) if row else None

    def list_runs(self, limit: int = 20) -> list[ResearchRun]:
        with self._conn() as conn:
            rows = conn.execute(
                self._run_select() + " ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def update_run(self, run_id: str, **fields) -> ResearchRun | None:
        allowed = {
            "status",
            "collector_status",
            "normalizer_status",
            "auditor_status",
            "ingestor_status",
            "indexer_status",
            "discovered_count",
            "fetched_count",
            "candidate_count",
            "promoted_count",
            "indexed_count",
            "error",
            "completed_at",
        }
        updates = []
        params: list[object] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "status" and value not in RUN_STATUSES:
                raise ValueError("Invalid run status")
            if key.endswith("_status") and value not in AGENT_STATUSES:
                raise ValueError("Invalid agent status")
            updates.append(f"{key} = ?")
            params.append(value)
        if not updates:
            return self.get_run(run_id)
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(run_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE research_runs SET {', '.join(updates)} WHERE id = ?",
                params,
            )
        return self.get_run(run_id)

    def add_run_event(
        self,
        run_id: str,
        *,
        agent: str,
        level: str,
        message: str,
        payload: dict | None = None,
    ) -> ResearchRunEvent:
        level = (level or "INFO").upper()
        if level not in EVENT_LEVELS:
            raise ValueError("Invalid event level")
        event_id = str(uuid.uuid4())
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO research_run_events (
                    id, run_id, agent, level, message, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    run_id,
                    agent,
                    level,
                    message,
                    _json_obj(payload),
                    now,
                ),
            )
        return self.get_run_event(event_id)

    def get_run_event(self, event_id: str) -> ResearchRunEvent | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, run_id, agent, level, message, payload_json, created_at
                FROM research_run_events WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
        return self._event_from_row(row) if row else None

    def list_run_events(self, run_id: str, limit: int = 200) -> list[ResearchRunEvent]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, agent, level, message, payload_json, created_at
                FROM research_run_events
                WHERE run_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (run_id, max(1, min(int(limit), 1000))),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def create_crawl_run(
        self,
        *,
        client_scope: str,
        client_code: str | None,
        source_ids: list[str],
        seed_queries: list[str],
        max_pages_per_source: int = 2,
        max_topics: int = 40,
        auto_queue_runs: bool = True,
        auto_promote: bool = True,
        auto_index: bool = False,
    ) -> CrawlRun:
        if client_scope not in {"standard", "client"}:
            raise ValueError("client_scope must be standard or client")
        if client_scope == "client" and not client_code:
            raise ValueError("client_code is required for client scope")
        source_ids = [s.strip() for s in source_ids if s and s.strip()]
        if not source_ids:
            raise ValueError("At least one source is required")
        seed_queries = [q.strip() for q in seed_queries if q and q.strip()]
        if not seed_queries:
            raise ValueError("At least one seed query is required")

        crawl_id = str(uuid.uuid4())
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO crawl_runs (
                    id, client_scope, client_code, source_ids_json, seed_queries_json,
                    max_pages_per_source, max_topics, auto_queue_runs, auto_promote, auto_index,
                    status, scout_status, crawler_status, topic_status, queue_status,
                    discovered_url_count, fetched_page_count, discovered_topic_count, queued_run_count,
                    error, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', 'PENDING', 'PENDING', 'PENDING', 'PENDING',
                          0, 0, 0, 0, NULL, ?, ?, NULL)
                """,
                (
                    crawl_id,
                    client_scope,
                    client_code,
                    json.dumps(source_ids),
                    json.dumps(seed_queries),
                    max(1, min(int(max_pages_per_source), 20)),
                    max(1, min(int(max_topics), 500)),
                    1 if auto_queue_runs else 0,
                    1 if auto_promote else 0,
                    1 if auto_index and auto_promote else 0,
                    now,
                    now,
                ),
            )
        return self.get_crawl_run(crawl_id)

    def get_crawl_run(self, crawl_id: str) -> CrawlRun | None:
        with self._conn() as conn:
            row = conn.execute(
                self._crawl_run_select() + " WHERE id = ?",
                (crawl_id,),
            ).fetchone()
        return self._crawl_run_from_row(row) if row else None

    def list_crawl_runs(self, limit: int = 20) -> list[CrawlRun]:
        with self._conn() as conn:
            rows = conn.execute(
                self._crawl_run_select() + " ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [self._crawl_run_from_row(row) for row in rows]

    def update_crawl_run(self, crawl_id: str, **fields) -> CrawlRun | None:
        allowed = {
            "status",
            "scout_status",
            "crawler_status",
            "topic_status",
            "queue_status",
            "discovered_url_count",
            "fetched_page_count",
            "discovered_topic_count",
            "queued_run_count",
            "error",
            "completed_at",
        }
        updates = []
        params: list[object] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "status" and value not in RUN_STATUSES:
                raise ValueError("Invalid crawl status")
            if key.endswith("_status") and value not in AGENT_STATUSES:
                raise ValueError("Invalid crawl agent status")
            updates.append(f"{key} = ?")
            params.append(value)
        if not updates:
            return self.get_crawl_run(crawl_id)
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(crawl_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE crawl_runs SET {', '.join(updates)} WHERE id = ?",
                params,
            )
        return self.get_crawl_run(crawl_id)

    def add_crawl_event(
        self,
        crawl_id: str,
        *,
        agent: str,
        level: str,
        message: str,
        payload: dict | None = None,
    ) -> CrawlRunEvent:
        level = (level or "INFO").upper()
        if level not in EVENT_LEVELS:
            raise ValueError("Invalid event level")
        event_id = str(uuid.uuid4())
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO crawl_run_events (
                    id, crawl_id, agent, level, message, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, crawl_id, agent, level, message, _json_obj(payload), now),
            )
        return self.get_crawl_event(event_id)

    def get_crawl_event(self, event_id: str) -> CrawlRunEvent | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, crawl_id, agent, level, message, payload_json, created_at
                FROM crawl_run_events WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
        return self._crawl_event_from_row(row) if row else None

    def list_crawl_events(self, crawl_id: str, limit: int = 300) -> list[CrawlRunEvent]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, crawl_id, agent, level, message, payload_json, created_at
                FROM crawl_run_events
                WHERE crawl_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (crawl_id, max(1, min(int(limit), 1000))),
            ).fetchall()
        return [self._crawl_event_from_row(row) for row in rows]

    def create_discovered_topic(
        self,
        *,
        source: ResearchSource,
        url: str | None,
        title: str,
        topic: str,
        category: str | None,
        objects: list[str],
        tags: list[str],
        confidence_score: float,
        status: str = "DISCOVERED",
    ) -> tuple[DiscoveredTopic, bool]:
        if status not in DISCOVERED_TOPIC_STATUSES:
            raise ValueError("Invalid discovered topic status")
        title = (title or "").strip()
        topic = (topic or "").strip()
        if not title:
            raise ValueError("title is required")
        if not topic:
            raise ValueError("topic is required")
        content_hash = _hash_topic(topic)
        now = _now()
        topic_id = str(uuid.uuid4())
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM discovered_topics WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE discovered_topics SET updated_at = ? WHERE id = ?",
                    (now, existing[0]),
                )
                return self.get_discovered_topic(existing[0]), False
            conn.execute(
                """
                INSERT INTO discovered_topics (
                    id, source_id, source_name, url, title, topic, category,
                    objects_json, tags_json, confidence_score, status, queued_run_id,
                    content_hash, first_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    topic_id,
                    source.id,
                    source.name,
                    url,
                    title,
                    topic,
                    category,
                    _json_list(objects),
                    _json_list(tags),
                    float(confidence_score),
                    status,
                    content_hash,
                    now,
                    now,
                ),
            )
        return self.get_discovered_topic(topic_id), True

    def get_discovered_topic(self, topic_id: str) -> DiscoveredTopic | None:
        with self._conn() as conn:
            row = conn.execute(
                self._discovered_topic_select() + " WHERE id = ?",
                (topic_id,),
            ).fetchone()
        return self._discovered_topic_from_row(row) if row else None

    def list_discovered_topics(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[DiscoveredTopic]:
        query = self._discovered_topic_select()
        params: list[object] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._discovered_topic_from_row(row) for row in rows]

    def update_discovered_topic(
        self,
        topic_id: str,
        *,
        status: str | None = None,
        queued_run_id: str | None = None,
    ) -> DiscoveredTopic | None:
        updates = ["updated_at = ?"]
        params: list[object] = [_now()]
        if status is not None:
            if status not in DISCOVERED_TOPIC_STATUSES:
                raise ValueError("Invalid discovered topic status")
            updates.append("status = ?")
            params.append(status)
        if queued_run_id is not None:
            updates.append("queued_run_id = ?")
            params.append(queued_run_id)
        params.append(topic_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE discovered_topics SET {', '.join(updates)} WHERE id = ?",
                params,
            )
        return self.get_discovered_topic(topic_id)

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")

    @staticmethod
    def _source_from_row(row) -> ResearchSource:
        return ResearchSource(
            id=row[0],
            priority=row[1],
            name=row[2],
            kind=row[3],
            tier=row[4],
            base_url=row[5] or "",
            usage_policy=row[6],
            enabled=row[7],
            notes=row[8],
            created_at=row[9],
            updated_at=row[10],
        )

    @staticmethod
    def _candidate_select() -> str:
        return """
            SELECT id, source_id, source_name, client_scope, client_code, url,
                   title, raw_excerpt, kb_type, content_markdown, tags_json,
                   sap_objects_json, signals_json, sources_json, confidence_score,
                   copyright_risk, audit_status, audit_notes, status, promoted_kb_id,
                   content_hash, created_at, updated_at
            FROM kb_candidates
        """

    @staticmethod
    def _candidate_from_row(row) -> KBCandidate:
        return KBCandidate(
            id=row[0],
            source_id=row[1],
            source_name=row[2],
            client_scope=row[3],
            client_code=row[4],
            url=row[5],
            title=row[6],
            raw_excerpt=row[7],
            kb_type=row[8],
            content_markdown=row[9],
            tags_json=row[10],
            sap_objects_json=row[11],
            signals_json=row[12],
            sources_json=row[13],
            confidence_score=row[14],
            copyright_risk=row[15],
            audit_status=row[16],
            audit_notes=row[17],
            status=row[18],
            promoted_kb_id=row[19],
            content_hash=row[20],
            created_at=row[21],
            updated_at=row[22],
        )

    @staticmethod
    def _run_select() -> str:
        return """
            SELECT id, topic, client_scope, client_code, source_ids_json,
                   max_results_per_source, auto_promote, auto_index, status,
                   collector_status, normalizer_status, auditor_status, ingestor_status, indexer_status,
                   discovered_count, fetched_count, candidate_count, promoted_count, indexed_count,
                   error, created_at, updated_at, completed_at
            FROM research_runs
        """

    @staticmethod
    def _run_from_row(row) -> ResearchRun:
        return ResearchRun(
            id=row[0],
            topic=row[1],
            client_scope=row[2],
            client_code=row[3],
            source_ids_json=row[4],
            max_results_per_source=row[5],
            auto_promote=row[6],
            auto_index=row[7],
            status=row[8],
            collector_status=row[9],
            normalizer_status=row[10],
            auditor_status=row[11],
            ingestor_status=row[12],
            indexer_status=row[13],
            discovered_count=row[14],
            fetched_count=row[15],
            candidate_count=row[16],
            promoted_count=row[17],
            indexed_count=row[18],
            error=row[19],
            created_at=row[20],
            updated_at=row[21],
            completed_at=row[22],
        )

    @staticmethod
    def _event_from_row(row) -> ResearchRunEvent:
        return ResearchRunEvent(
            id=row[0],
            run_id=row[1],
            agent=row[2],
            level=row[3],
            message=row[4],
            payload_json=row[5],
            created_at=row[6],
        )

    @staticmethod
    def _crawl_run_select() -> str:
        return """
            SELECT id, client_scope, client_code, source_ids_json, seed_queries_json,
                   max_pages_per_source, max_topics, auto_queue_runs, auto_promote, auto_index,
                   status, scout_status, crawler_status, topic_status, queue_status,
                   discovered_url_count, fetched_page_count, discovered_topic_count, queued_run_count,
                   error, created_at, updated_at, completed_at
            FROM crawl_runs
        """

    @staticmethod
    def _crawl_run_from_row(row) -> CrawlRun:
        return CrawlRun(
            id=row[0],
            client_scope=row[1],
            client_code=row[2],
            source_ids_json=row[3],
            seed_queries_json=row[4],
            max_pages_per_source=row[5],
            max_topics=row[6],
            auto_queue_runs=row[7],
            auto_promote=row[8],
            auto_index=row[9],
            status=row[10],
            scout_status=row[11],
            crawler_status=row[12],
            topic_status=row[13],
            queue_status=row[14],
            discovered_url_count=row[15],
            fetched_page_count=row[16],
            discovered_topic_count=row[17],
            queued_run_count=row[18],
            error=row[19],
            created_at=row[20],
            updated_at=row[21],
            completed_at=row[22],
        )

    @staticmethod
    def _crawl_event_from_row(row) -> CrawlRunEvent:
        return CrawlRunEvent(
            id=row[0],
            crawl_id=row[1],
            agent=row[2],
            level=row[3],
            message=row[4],
            payload_json=row[5],
            created_at=row[6],
        )

    @staticmethod
    def _discovered_topic_select() -> str:
        return """
            SELECT id, source_id, source_name, url, title, topic, category,
                   objects_json, tags_json, confidence_score, status, queued_run_id,
                   content_hash, first_seen_at, updated_at
            FROM discovered_topics
        """

    @staticmethod
    def _discovered_topic_from_row(row) -> DiscoveredTopic:
        return DiscoveredTopic(
            id=row[0],
            source_id=row[1],
            source_name=row[2],
            url=row[3],
            title=row[4],
            topic=row[5],
            category=row[6],
            objects_json=row[7],
            tags_json=row[8],
            confidence_score=row[9],
            status=row[10],
            queued_run_id=row[11],
            content_hash=row[12],
            first_seen_at=row[13],
            updated_at=row[14],
        )
