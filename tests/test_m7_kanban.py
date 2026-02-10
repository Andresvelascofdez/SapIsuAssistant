"""
M7 Acceptance Tests: Kanban (Independent)

Tests confirm Kanban uses its own DB and never queries assistant DB per PLAN.md section 13.
"""
import json
import sqlite3

import pytest

from src.kanban.storage.kanban_repository import (
    KanbanRepository,
    Ticket,
    TicketHistoryEntry,
    TicketPriority,
    TicketStatus,
)


def test_kanban_init_creates_schema(tmp_path):
    """Test kanban repository initializes tables."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t[0] for t in tables]

        assert "tickets" in table_names
        assert "ticket_history" in table_names


def test_create_ticket(tmp_path):
    """Test ticket creation."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    ticket = repo.create_ticket(
        title="Fix IDEX processing error",
        priority=TicketPriority.HIGH,
        ticket_id="INC-001",
        notes="Customer reported issue",
        links=["https://example.com/inc-001"],
        tags=["IDEX", "urgent"],
    )

    assert ticket.id
    assert ticket.ticket_id == "INC-001"
    assert ticket.title == "Fix IDEX processing error"
    assert ticket.status == TicketStatus.OPEN
    assert ticket.priority == TicketPriority.HIGH
    assert ticket.notes == "Customer reported issue"

    links = json.loads(ticket.links_json)
    assert links == ["https://example.com/inc-001"]

    tags = json.loads(ticket.tags_json)
    assert tags == ["IDEX", "urgent"]


def test_create_ticket_defaults(tmp_path):
    """Test ticket creation with defaults."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    ticket = repo.create_ticket(title="Simple ticket")

    assert ticket.status == TicketStatus.OPEN
    assert ticket.priority == TicketPriority.MEDIUM
    assert ticket.ticket_id is None
    assert ticket.notes is None
    assert json.loads(ticket.links_json) == []
    assert json.loads(ticket.tags_json) == []


def test_get_by_id(tmp_path):
    """Test getting ticket by ID."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    created = repo.create_ticket(title="Test ticket")
    fetched = repo.get_by_id(created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.title == "Test ticket"

    # Non-existent
    assert repo.get_by_id("nonexistent") is None


def test_update_status(tmp_path):
    """Test updating ticket status."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    ticket = repo.create_ticket(title="Status test")
    assert ticket.status == TicketStatus.OPEN

    updated = repo.update_status(ticket.id, TicketStatus.IN_PROGRESS)
    assert updated.status == TicketStatus.IN_PROGRESS
    assert updated.closed_at is None

    # Move to DONE (should set closed_at)
    done = repo.update_status(ticket.id, TicketStatus.DONE)
    assert done.status == TicketStatus.DONE
    assert done.closed_at is not None


def test_update_status_nonexistent(tmp_path):
    """Test updating status of nonexistent ticket."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    result = repo.update_status("nonexistent", TicketStatus.DONE)
    assert result is None


def test_update_ticket_fields(tmp_path):
    """Test updating ticket fields."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    ticket = repo.create_ticket(title="Original title", priority=TicketPriority.LOW)

    updated = repo.update_ticket(
        ticket.id,
        title="Updated title",
        priority=TicketPriority.CRITICAL,
        notes="Added notes",
        tags=["new-tag"],
    )

    assert updated.title == "Updated title"
    assert updated.priority == TicketPriority.CRITICAL
    assert updated.notes == "Added notes"
    assert json.loads(updated.tags_json) == ["new-tag"]


def test_list_tickets(tmp_path):
    """Test listing tickets."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    repo.create_ticket(title="Ticket 1")
    repo.create_ticket(title="Ticket 2")
    ticket3 = repo.create_ticket(title="Ticket 3")
    repo.update_status(ticket3.id, TicketStatus.DONE)

    all_tickets = repo.list_tickets()
    assert len(all_tickets) == 3

    open_tickets = repo.list_tickets(status=TicketStatus.OPEN)
    assert len(open_tickets) == 2

    done_tickets = repo.list_tickets(status=TicketStatus.DONE)
    assert len(done_tickets) == 1
    assert done_tickets[0].title == "Ticket 3"


def test_ticket_history(tmp_path):
    """Test ticket status history tracking."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    ticket = repo.create_ticket(title="History test")
    repo.update_status(ticket.id, TicketStatus.IN_PROGRESS)
    repo.update_status(ticket.id, TicketStatus.WAITING)
    repo.update_status(ticket.id, TicketStatus.DONE)

    history = repo.get_history(ticket.id)
    assert len(history) == 4  # OPEN + 3 transitions

    assert history[0].from_status is None
    assert history[0].to_status == TicketStatus.OPEN

    assert history[1].from_status == TicketStatus.OPEN
    assert history[1].to_status == TicketStatus.IN_PROGRESS

    assert history[2].from_status == TicketStatus.IN_PROGRESS
    assert history[2].to_status == TicketStatus.WAITING

    assert history[3].from_status == TicketStatus.WAITING
    assert history[3].to_status == TicketStatus.DONE


def test_kanban_uses_own_database(tmp_path):
    """
    Critical test: Kanban must use its own DB and never touch assistant DB.

    Per PLAN.md section 15: Kanban is independent and never used as assistant knowledge.
    """
    # Create separate databases
    kanban_db = tmp_path / "kanban.sqlite"
    assistant_db = tmp_path / "assistant_kb.sqlite"

    kanban_repo = KanbanRepository(kanban_db)

    # Create ticket in kanban
    ticket = kanban_repo.create_ticket(title="Kanban ticket")
    assert ticket is not None

    # Verify kanban DB has the ticket
    with sqlite3.connect(kanban_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        assert count == 1

    # Verify assistant DB was never created/touched
    assert not assistant_db.exists(), "Kanban must never create or touch assistant DB"


def test_kanban_db_has_no_assistant_tables(tmp_path):
    """Test kanban DB does not contain any assistant tables."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    # Create some data
    repo.create_ticket(title="Test")

    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}

        # Must only have kanban tables
        assert "tickets" in table_names
        assert "ticket_history" in table_names

        # Must NOT have assistant tables
        assert "kb_items" not in table_names
        assert "ingestions" not in table_names
