"""
Ingestion repository per PLAN.md section 5.1.
"""
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from .models import Ingestion, IngestionStatus


class IngestionRepository:
    """Repository for ingestion records."""

    def __init__(self, db_path: Path):
        """
        Initialize repository.

        Args:
            db_path: Path to assistant_kb.sqlite
        """
        self.db_path = Path(db_path)
        self._init_schema()

    def _init_schema(self):
        """Initialize ingestions table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ingestions (
                    ingestion_id TEXT PRIMARY KEY,
                    client_scope TEXT NOT NULL,
                    client_code TEXT NULL,
                    input_kind TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    input_name TEXT NULL,
                    status TEXT NOT NULL,
                    model_used TEXT NOT NULL,
                    reasoning_effort TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ingestions_scope_client
                ON ingestions(client_scope, client_code)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ingestions_status
                ON ingestions(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ingestions_input_hash
                ON ingestions(input_hash)
            """)
            conn.commit()

    def create(
        self,
        client_scope: str,
        client_code: Optional[str],
        input_kind: str,
        input_hash: str,
        input_name: Optional[str],
        model_used: str,
        reasoning_effort: str,
        status: IngestionStatus = IngestionStatus.DRAFT,
    ) -> Ingestion:
        """Create new ingestion record."""
        ingestion_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO ingestions (
                    ingestion_id, client_scope, client_code, input_kind, input_hash,
                    input_name, status, model_used, reasoning_effort, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ingestion_id,
                client_scope,
                client_code,
                input_kind,
                input_hash,
                input_name,
                status.value,
                model_used,
                reasoning_effort,
                now,
                now,
            ))
            conn.commit()

        return self.get_by_id(ingestion_id)

    def get_by_id(self, ingestion_id: str) -> Optional[Ingestion]:
        """Retrieve ingestion by ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT ingestion_id, client_scope, client_code, input_kind, input_hash,
                       input_name, status, model_used, reasoning_effort, created_at, updated_at
                FROM ingestions
                WHERE ingestion_id = ?
                """,
                (ingestion_id,)
            ).fetchone()

            if row:
                return Ingestion(
                    ingestion_id=row[0],
                    client_scope=row[1],
                    client_code=row[2],
                    input_kind=row[3],
                    input_hash=row[4],
                    input_name=row[5],
                    status=row[6],
                    model_used=row[7],
                    reasoning_effort=row[8],
                    created_at=row[9],
                    updated_at=row[10],
                )

        return None

    def update_status(self, ingestion_id: str, status: IngestionStatus) -> Optional[Ingestion]:
        """Update ingestion status."""
        now = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE ingestions SET status = ?, updated_at = ? WHERE ingestion_id = ?",
                (status.value, now, ingestion_id)
            )
            conn.commit()

        return self.get_by_id(ingestion_id)

    def list_by_scope(
        self,
        client_scope: str,
        client_code: Optional[str] = None,
        status: Optional[IngestionStatus] = None,
    ) -> list[Ingestion]:
        """
        List ingestions by scope and optional status filter.

        Args:
            client_scope: "standard" or "client"
            client_code: Client code (required if client_scope="client")
            status: Optional status filter

        Returns:
            List of ingestions
        """
        with sqlite3.connect(self.db_path) as conn:
            if status:
                query = """
                    SELECT ingestion_id, client_scope, client_code, input_kind, input_hash,
                           input_name, status, model_used, reasoning_effort, created_at, updated_at
                    FROM ingestions
                    WHERE client_scope = ?
                      AND (? IS NULL AND client_code IS NULL OR client_code = ?)
                      AND status = ?
                    ORDER BY created_at DESC
                """
                rows = conn.execute(query, (client_scope, client_code, client_code, status.value)).fetchall()
            else:
                query = """
                    SELECT ingestion_id, client_scope, client_code, input_kind, input_hash,
                           input_name, status, model_used, reasoning_effort, created_at, updated_at
                    FROM ingestions
                    WHERE client_scope = ?
                      AND (? IS NULL AND client_code IS NULL OR client_code = ?)
                    ORDER BY created_at DESC
                """
                rows = conn.execute(query, (client_scope, client_code, client_code)).fetchall()

            return [
                Ingestion(
                    ingestion_id=r[0],
                    client_scope=r[1],
                    client_code=r[2],
                    input_kind=r[3],
                    input_hash=r[4],
                    input_name=r[5],
                    status=r[6],
                    model_used=r[7],
                    reasoning_effort=r[8],
                    created_at=r[9],
                    updated_at=r[10],
                )
                for r in rows
            ]
