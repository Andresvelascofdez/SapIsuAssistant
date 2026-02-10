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


class TicketStatus:
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    DONE = "DONE"
    CLOSED = "CLOSED"


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

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._init_schema()

    def _init_schema(self):
        """Initialize kanban tables."""
        with sqlite3.connect(self.db_path) as conn:
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
            conn.commit()

    def create_ticket(
        self,
        title: str,
        priority: str = TicketPriority.MEDIUM,
        ticket_id: str | None = None,
        notes: str | None = None,
        links: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Ticket:
        """Create a new ticket."""
        import json

        internal_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        status = TicketStatus.OPEN

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

            closed_at = now if new_status in (TicketStatus.DONE, TicketStatus.CLOSED) else None

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
