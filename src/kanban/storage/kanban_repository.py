"""
Kanban ticket repository per PLAN.md section 6.

Independent from assistant - uses its own database.
"""
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional


DEFAULT_COLUMNS = [
    {"name": "NO_ANALIZADO", "display_name": "No analizado", "position": 0},
    {"name": "EN_PROGRESO", "display_name": "En progreso", "position": 1},
    {"name": "MAS_INFO", "display_name": "Mas info", "position": 2},
    {"name": "TESTING", "display_name": "Testing", "position": 3},
    {"name": "PENDIENTE_DE_TRANSPORTE", "display_name": "Pendiente de transporte", "position": 4},
    {"name": "ANALIZADO_PENDIENTE_RESPUESTA", "display_name": "Analizado - Pendiente respuesta", "position": 5},
    {"name": "ANALIZADO", "display_name": "Analizado", "position": 6},
    {"name": "CERRADO", "display_name": "Cerrado", "position": 7},
]


@dataclass
class KanbanColumn:
    id: int
    name: str
    display_name: str
    position: int
    created_at: str


class TicketStatus:
    """Status constants matching default column names."""
    NO_ANALIZADO = "NO_ANALIZADO"
    EN_PROGRESO = "EN_PROGRESO"
    MAS_INFO = "MAS_INFO"
    TESTING = "TESTING"
    PENDIENTE_DE_TRANSPORTE = "PENDIENTE_DE_TRANSPORTE"
    ANALIZADO_PENDIENTE_RESPUESTA = "ANALIZADO_PENDIENTE_RESPUESTA"
    ANALIZADO = "ANALIZADO"
    CERRADO = "CERRADO"


class TicketPriority:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Ticket:
    """Ticket entity per PLAN.md section 6."""
    id: str
    ticket_id: str | None
    title: str
    status: str
    priority: str
    notes: str | None
    links_json: str
    tags_json: str
    created_at: str
    updated_at: str
    closed_at: str | None


@dataclass
class TicketHistoryEntry:
    """Ticket history entry per PLAN.md section 6."""
    id: str
    ticket_id: str
    from_status: str | None
    to_status: str
    changed_at: str


class KanbanRepository:
    """
    Kanban repository per PLAN.md section 6.

    Must use its own database and never query assistant DB per PLAN.md section 15.
    """

    def __init__(self, db_path: Path, seed_columns: bool = True):
        self.db_path = Path(db_path)
        self._seed_columns = seed_columns
        self._init_schema()

    def _init_schema(self):
        """Initialize kanban tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kanban_columns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY,
                    ticket_id TEXT,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    notes TEXT,
                    links_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    closed_at TEXT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_history (
                    id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tickets_status
                ON tickets(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ticket_history_ticket_id
                ON ticket_history(ticket_id)
            """)

            # Seed default columns only if requested (global DB)
            if self._seed_columns:
                count = conn.execute("SELECT COUNT(*) FROM kanban_columns").fetchone()[0]
                if count == 0:
                    now = datetime.now(UTC).isoformat()
                    for col in DEFAULT_COLUMNS:
                        conn.execute(
                            "INSERT INTO kanban_columns (name, display_name, position, created_at) VALUES (?, ?, ?, ?)",
                            (col["name"], col["display_name"], col["position"], now),
                        )

            conn.commit()

    def create_ticket(
        self,
        title: str,
        priority: str = TicketPriority.MEDIUM,
        ticket_id: str | None = None,
        notes: str | None = None,
        links: list[str] | None = None,
        tags: list[str] | None = None,
        status: str = "EN_PROGRESO",
    ) -> Ticket:
        """Create a new ticket."""
        import json

        internal_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO tickets (id, ticket_id, title, status, priority, notes, links_json, tags_json, created_at, updated_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                internal_id,
                ticket_id,
                title,
                status,
                priority,
                notes,
                json.dumps(links or []),
                json.dumps(tags or []),
                now,
                now,
                None,
            ))

            # Record history
            conn.execute("""
                INSERT INTO ticket_history (id, ticket_id, from_status, to_status, changed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), internal_id, None, status, now))

            conn.commit()

        return self.get_by_id(internal_id)

    def get_by_id(self, internal_id: str) -> Optional[Ticket]:
        """Get ticket by internal ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, ticket_id, title, status, priority, notes, links_json, tags_json, created_at, updated_at, closed_at FROM tickets WHERE id = ?",
                (internal_id,)
            ).fetchone()

            if row:
                return Ticket(*row)

        return None

    def update_status(self, internal_id: str, new_status: str) -> Optional[Ticket]:
        """Update ticket status and record history."""
        now = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            # Get current status
            row = conn.execute(
                "SELECT status FROM tickets WHERE id = ?", (internal_id,)
            ).fetchone()

            if not row:
                return None

            old_status = row[0]

            closed_at = now if new_status in ("DONE", "CLOSED", "CERRADO") else None

            conn.execute(
                "UPDATE tickets SET status = ?, updated_at = ?, closed_at = COALESCE(?, closed_at) WHERE id = ?",
                (new_status, now, closed_at, internal_id)
            )

            # Record history
            conn.execute("""
                INSERT INTO ticket_history (id, ticket_id, from_status, to_status, changed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), internal_id, old_status, new_status, now))

            conn.commit()

        return self.get_by_id(internal_id)

    def update_ticket(
        self,
        internal_id: str,
        title: str | None = None,
        priority: str | None = None,
        notes: str | None = None,
        links: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Optional[Ticket]:
        """Update ticket fields."""
        import json

        now = datetime.now(UTC).isoformat()
        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if links is not None:
            updates.append("links_json = ?")
            params.append(json.dumps(links))
        if tags is not None:
            updates.append("tags_json = ?")
            params.append(json.dumps(tags))

        if not updates:
            return self.get_by_id(internal_id)

        updates.append("updated_at = ?")
        params.append(now)
        params.append(internal_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE tickets SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()

        return self.get_by_id(internal_id)

    def list_tickets(self, status: str | None = None) -> list[Ticket]:
        """List tickets, optionally filtered by status."""
        with sqlite3.connect(self.db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT id, ticket_id, title, status, priority, notes, links_json, tags_json, created_at, updated_at, closed_at FROM tickets WHERE status = ? ORDER BY created_at DESC",
                    (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, ticket_id, title, status, priority, notes, links_json, tags_json, created_at, updated_at, closed_at FROM tickets ORDER BY created_at DESC"
                ).fetchall()

            return [Ticket(*r) for r in rows]

    def get_history(self, internal_id: str) -> list[TicketHistoryEntry]:
        """Get ticket status history."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, ticket_id, from_status, to_status, changed_at FROM ticket_history WHERE ticket_id = ? ORDER BY changed_at ASC",
                (internal_id,)
            ).fetchall()

            return [TicketHistoryEntry(*r) for r in rows]

    # ── Column management ──

    def list_columns(self) -> list[KanbanColumn]:
        """List all columns ordered by position."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, name, display_name, position, created_at FROM kanban_columns ORDER BY position ASC"
            ).fetchall()
            return [KanbanColumn(*r) for r in rows]

    def create_column(self, name: str, display_name: str) -> KanbanColumn:
        """Create a new column at the end."""
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            max_pos = conn.execute("SELECT COALESCE(MAX(position), -1) FROM kanban_columns").fetchone()[0]
            conn.execute(
                "INSERT INTO kanban_columns (name, display_name, position, created_at) VALUES (?, ?, ?, ?)",
                (name, display_name, max_pos + 1, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, name, display_name, position, created_at FROM kanban_columns WHERE name = ?",
                (name,),
            ).fetchone()
            return KanbanColumn(*row)

    def rename_column(self, col_id: int, display_name: str) -> Optional[KanbanColumn]:
        """Rename a column's display name."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE kanban_columns SET display_name = ? WHERE id = ?",
                (display_name, col_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, name, display_name, position, created_at FROM kanban_columns WHERE id = ?",
                (col_id,),
            ).fetchone()
            return KanbanColumn(*row) if row else None

    def delete_column(self, col_id: int) -> bool:
        """Delete a column. Returns False if column has tickets."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT name FROM kanban_columns WHERE id = ?", (col_id,)
            ).fetchone()
            if not row:
                return False

            col_name = row[0]
            ticket_count = conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE status = ?", (col_name,)
            ).fetchone()[0]

            if ticket_count > 0:
                raise ValueError(f"Column '{col_name}' has {ticket_count} ticket(s). Move them first.")

            conn.execute("DELETE FROM kanban_columns WHERE id = ?", (col_id,))
            conn.commit()
            return True

    def reorder_columns(self, ordered_ids: list[int]) -> list[KanbanColumn]:
        """Reorder columns by providing IDs in desired order."""
        with sqlite3.connect(self.db_path) as conn:
            for position, col_id in enumerate(ordered_ids):
                conn.execute(
                    "UPDATE kanban_columns SET position = ? WHERE id = ?",
                    (position, col_id),
                )
            conn.commit()
        return self.list_columns()
