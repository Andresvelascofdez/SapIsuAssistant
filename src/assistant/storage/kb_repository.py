"""
KB Items repository with dedupe and versioning logic per PLAN.md section 5.1.
"""
import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from .models import KBItem, KBItemStatus, KBItemType


class KBItemRepository:
    """
    Repository for KB items with dedupe and versioning.

    Dedupe rule (PLAN.md section 5.1):
    - Same type + normalized_title + same content_hash -> no duplicate
    - Same type + normalized_title + different content_hash -> new version
    """

    def __init__(self, db_path: Path):
        """
        Initialize repository.

        Args:
            db_path: Path to assistant_kb.sqlite
        """
        self.db_path = Path(db_path)
        self._init_schema()

    def _init_schema(self):
        """Initialize kb_items table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kb_items (
                    kb_id TEXT PRIMARY KEY,
                    client_scope TEXT NOT NULL,
                    client_code TEXT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_markdown TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    sap_objects_json TEXT NOT NULL,
                    signals_json TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kb_items_scope_client
                ON kb_items(client_scope, client_code)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kb_items_type_title
                ON kb_items(type, title)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kb_items_status
                ON kb_items(status)
            """)
            conn.commit()

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for deduplication."""
        return title.strip().lower()

    @staticmethod
    def _compute_content_hash(content_markdown: str, title: str, item_type: str) -> str:
        """Compute SHA256 hash of content + title + type."""
        combined = f"{item_type}|{title}|{content_markdown}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def create_or_update(
        self,
        client_scope: str,
        client_code: Optional[str],
        item_type: KBItemType,
        title: str,
        content_markdown: str,
        tags: list[str],
        sap_objects: list[str],
        signals: dict,
        sources: dict,
        status: KBItemStatus = KBItemStatus.DRAFT,
    ) -> tuple[KBItem, bool]:
        """
        Create new KB item or update existing one (versioning).

        Returns:
            (KBItem, is_new): Created/updated item and whether it's new (True) or updated (False)

        Dedupe logic:
        - If same type + normalized_title + same content_hash exists in same scope -> return existing
        - If same type + normalized_title + different content_hash exists -> increment version
        - Otherwise -> create new item with version 1
        """
        normalized_title = self._normalize_title(title)
        content_hash = self._compute_content_hash(content_markdown, title, item_type.value)

        with sqlite3.connect(self.db_path) as conn:
            # Check for existing item with same type + normalized title in same scope
            query = """
                SELECT kb_id, version, content_hash, status, created_at, updated_at
                FROM kb_items
                WHERE client_scope = ?
                  AND (? IS NULL AND client_code IS NULL OR client_code = ?)
                  AND type = ?
                  AND LOWER(TRIM(title)) = ?
                ORDER BY version DESC
                LIMIT 1
            """
            row = conn.execute(
                query,
                (client_scope, client_code, client_code, item_type.value, normalized_title)
            ).fetchone()

            now = datetime.now(UTC).isoformat()

            if row:
                existing_kb_id, existing_version, existing_hash, existing_status, created_at, _ = row

                # Same content hash -> return existing (dedupe)
                if existing_hash == content_hash:
                    existing = self.get_by_id(existing_kb_id)
                    return existing, False

                # Different content hash -> increment version
                new_version = existing_version + 1
                kb_id = existing_kb_id  # Keep same kb_id for versioning
                is_new = False
            else:
                # New item
                kb_id = str(uuid.uuid4())
                new_version = 1
                created_at = now
                is_new = True

            # Insert or replace
            conn.execute("""
                INSERT OR REPLACE INTO kb_items (
                    kb_id, client_scope, client_code, type, title,
                    content_markdown, tags_json, sap_objects_json, signals_json, sources_json,
                    version, status, content_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                kb_id,
                client_scope,
                client_code,
                item_type.value,
                title,
                content_markdown,
                json.dumps(tags),
                json.dumps(sap_objects),
                json.dumps(signals),
                json.dumps(sources),
                new_version,
                status.value,
                content_hash,
                created_at,
                now,
            ))
            conn.commit()

            item = self.get_by_id(kb_id)
            return item, is_new

    def get_by_id(self, kb_id: str) -> Optional[KBItem]:
        """Retrieve KB item by ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT kb_id, client_scope, client_code, type, title,
                       content_markdown, tags_json, sap_objects_json, signals_json, sources_json,
                       version, status, content_hash, created_at, updated_at
                FROM kb_items
                WHERE kb_id = ?
                """,
                (kb_id,)
            ).fetchone()

            if row:
                return KBItem(
                    kb_id=row[0],
                    client_scope=row[1],
                    client_code=row[2],
                    type=row[3],
                    title=row[4],
                    content_markdown=row[5],
                    tags_json=row[6],
                    sap_objects_json=row[7],
                    signals_json=row[8],
                    sources_json=row[9],
                    version=row[10],
                    status=row[11],
                    content_hash=row[12],
                    created_at=row[13],
                    updated_at=row[14],
                )

        return None

    def list_by_scope(
        self,
        client_scope: str,
        client_code: Optional[str] = None,
        status: Optional[KBItemStatus] = None,
    ) -> list[KBItem]:
        """
        List KB items by scope and optional status filter.

        Args:
            client_scope: "standard" or "client"
            client_code: Client code (required if client_scope="client")
            status: Optional status filter

        Returns:
            List of KB items
        """
        with sqlite3.connect(self.db_path) as conn:
            if status:
                query = """
                    SELECT kb_id, client_scope, client_code, type, title,
                           content_markdown, tags_json, sap_objects_json, signals_json, sources_json,
                           version, status, content_hash, created_at, updated_at
                    FROM kb_items
                    WHERE client_scope = ?
                      AND (? IS NULL AND client_code IS NULL OR client_code = ?)
                      AND status = ?
                    ORDER BY updated_at DESC
                """
                rows = conn.execute(query, (client_scope, client_code, client_code, status.value)).fetchall()
            else:
                query = """
                    SELECT kb_id, client_scope, client_code, type, title,
                           content_markdown, tags_json, sap_objects_json, signals_json, sources_json,
                           version, status, content_hash, created_at, updated_at
                    FROM kb_items
                    WHERE client_scope = ?
                      AND (? IS NULL AND client_code IS NULL OR client_code = ?)
                    ORDER BY updated_at DESC
                """
                rows = conn.execute(query, (client_scope, client_code, client_code)).fetchall()

            return [
                KBItem(
                    kb_id=r[0],
                    client_scope=r[1],
                    client_code=r[2],
                    type=r[3],
                    title=r[4],
                    content_markdown=r[5],
                    tags_json=r[6],
                    sap_objects_json=r[7],
                    signals_json=r[8],
                    sources_json=r[9],
                    version=r[10],
                    status=r[11],
                    content_hash=r[12],
                    created_at=r[13],
                    updated_at=r[14],
                )
                for r in rows
            ]

    def update_status(self, kb_id: str, status: KBItemStatus) -> Optional[KBItem]:
        """Update KB item status."""
        now = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE kb_items SET status = ?, updated_at = ? WHERE kb_id = ?",
                (status.value, now, kb_id)
            )
            conn.commit()

        return self.get_by_id(kb_id)
