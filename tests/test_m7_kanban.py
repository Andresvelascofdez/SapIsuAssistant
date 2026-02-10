"""
M7 Acceptance Tests: Kanban (Independent)

Tests confirm Kanban uses its own DB and never queries assistant DB per PLAN.md section 13.
"""
import json
import sqlite3

import pytest

from src.kanban.storage.kanban_repository import (
    KanbanColumn,
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
    assert ticket.status == TicketStatus.EN_PROGRESO
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

    assert ticket.status == TicketStatus.EN_PROGRESO
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
    assert ticket.status == TicketStatus.EN_PROGRESO

    updated = repo.update_status(ticket.id, TicketStatus.ANALIZADO)
    assert updated.status == TicketStatus.ANALIZADO
    assert updated.closed_at is None

    # Move to DONE (should set closed_at)
    done = repo.update_status(ticket.id, TicketStatus.CERRADO)
    assert done.status == TicketStatus.CERRADO
    assert done.closed_at is not None


def test_update_status_nonexistent(tmp_path):
    """Test updating status of nonexistent ticket."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    result = repo.update_status("nonexistent", TicketStatus.CERRADO)
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
    repo.update_status(ticket3.id, TicketStatus.CERRADO)

    all_tickets = repo.list_tickets()
    assert len(all_tickets) == 3

    open_tickets = repo.list_tickets(status=TicketStatus.EN_PROGRESO)
    assert len(open_tickets) == 2

    done_tickets = repo.list_tickets(status=TicketStatus.CERRADO)
    assert len(done_tickets) == 1
    assert done_tickets[0].title == "Ticket 3"


def test_ticket_history(tmp_path):
    """Test ticket status history tracking."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    ticket = repo.create_ticket(title="History test")
    repo.update_status(ticket.id, TicketStatus.ANALIZADO)
    repo.update_status(ticket.id, TicketStatus.TESTING)
    repo.update_status(ticket.id, TicketStatus.CERRADO)

    history = repo.get_history(ticket.id)
    assert len(history) == 4  # OPEN + 3 transitions

    assert history[0].from_status is None
    assert history[0].to_status == TicketStatus.EN_PROGRESO

    assert history[1].from_status == TicketStatus.EN_PROGRESO
    assert history[1].to_status == TicketStatus.ANALIZADO

    assert history[2].from_status == TicketStatus.ANALIZADO
    assert history[2].to_status == TicketStatus.TESTING

    assert history[3].from_status == TicketStatus.TESTING
    assert history[3].to_status == TicketStatus.CERRADO


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


# ── Column management tests ──


def test_init_seeds_default_columns(tmp_path):
    """Test that init creates the 7 default columns."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    columns = repo.list_columns()
    assert len(columns) == 7
    assert columns[0].name == "EN_PROGRESO"
    assert columns[0].display_name == "En progreso"
    assert columns[0].position == 0
    assert columns[1].name == "MAS_INFO"
    assert columns[2].name == "ANALIZADO"
    assert columns[3].name == "ANALIZADO_PENDIENTE_RESPUESTA"
    assert columns[4].name == "PENDIENTE_DE_TRANSPORTE"
    assert columns[5].name == "TESTING"
    assert columns[6].name == "CERRADO"


def test_list_columns_ordered(tmp_path):
    """Test columns are returned ordered by position."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    columns = repo.list_columns()
    positions = [c.position for c in columns]
    assert positions == sorted(positions)


def test_create_column(tmp_path):
    """Test creating a new column."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    col = repo.create_column("CUSTOM", "Custom Column")
    assert col.name == "CUSTOM"
    assert col.display_name == "Custom Column"
    assert col.position == 7  # After the 7 defaults (0-6)

    columns = repo.list_columns()
    assert len(columns) == 8
    assert columns[-1].name == "CUSTOM"


def test_create_column_duplicate_fails(tmp_path):
    """Test that creating a column with duplicate name fails."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    with pytest.raises(Exception):
        repo.create_column("EN_PROGRESO", "En progreso Again")


def test_rename_column(tmp_path):
    """Test renaming a column's display name."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    columns = repo.list_columns()
    col = columns[0]  # EN_PROGRESO
    renamed = repo.rename_column(col.id, "Nuevo Nombre")
    assert renamed.display_name == "Nuevo Nombre"
    assert renamed.name == "EN_PROGRESO"  # Internal name unchanged


def test_rename_column_nonexistent(tmp_path):
    """Test renaming a non-existent column returns None."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    result = repo.rename_column(9999, "Ghost")
    assert result is None


def test_delete_column(tmp_path):
    """Test deleting an empty column."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    col = repo.create_column("TEMP", "Temporary")
    assert repo.delete_column(col.id) is True

    columns = repo.list_columns()
    names = [c.name for c in columns]
    assert "TEMP" not in names


def test_delete_column_with_tickets_fails(tmp_path):
    """Test that deleting a column with tickets raises ValueError."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    # EN_PROGRESO column has tickets after creating one
    repo.create_ticket(title="Blocker ticket")

    columns = repo.list_columns()
    open_col = next(c for c in columns if c.name == "EN_PROGRESO")

    with pytest.raises(ValueError, match="ticket"):
        repo.delete_column(open_col.id)


def test_delete_column_nonexistent(tmp_path):
    """Test deleting a non-existent column returns False."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    assert repo.delete_column(9999) is False


def test_reorder_columns(tmp_path):
    """Test reordering columns."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    columns = repo.list_columns()
    # Reverse the order
    reversed_ids = [c.id for c in reversed(columns)]
    reordered = repo.reorder_columns(reversed_ids)

    assert reordered[0].name == "CERRADO"
    assert reordered[1].name == "TESTING"
    assert reordered[2].name == "PENDIENTE_DE_TRANSPORTE"
    assert reordered[3].name == "ANALIZADO_PENDIENTE_RESPUESTA"
    assert reordered[4].name == "ANALIZADO"
    assert reordered[5].name == "MAS_INFO"
    assert reordered[6].name == "EN_PROGRESO"

    # Verify positions are sequential
    for i, col in enumerate(reordered):
        assert col.position == i


def test_kanban_columns_table_exists(tmp_path):
    """Test that kanban_columns table exists in the database."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "kanban_columns" in table_names


def test_seed_columns_false(tmp_path):
    """Test that seed_columns=False does not create default columns."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path, seed_columns=False)

    columns = repo.list_columns()
    assert len(columns) == 0


def test_create_ticket_custom_status(tmp_path):
    """Test creating a ticket with a custom status."""
    db_path = tmp_path / "kanban.sqlite"
    repo = KanbanRepository(db_path)

    ticket = repo.create_ticket(title="Custom status ticket", status="TESTING")
    assert ticket.status == "TESTING"

    history = repo.get_history(ticket.id)
    assert len(history) == 1
    assert history[0].to_status == "TESTING"


def test_import_csv(tmp_path):
    """Test CSV import creates tickets in per-client databases."""
    import csv

    data_root = tmp_path / "data"
    data_root.mkdir()

    csv_path = tmp_path / "test_import.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "ID Tarea", "Nombre de tarea", "Cliente", "Estado",
            "Prioridad", "Responsable", "Horas", "Texto", "Tipo de tarea",
        ])
        writer.writeheader()
        writer.writerow({
            "ID Tarea": "T-001",
            "Nombre de tarea": "Fix IDEX timeout",
            "Cliente": "SWE",
            "Estado": "En progreso",
            "Prioridad": "Alta",
            "Responsable": "Juan",
            "Horas": "4",
            "Texto": "Check EA10",
            "Tipo de tarea": "Bug",
        })
        writer.writerow({
            "ID Tarea": "T-002",
            "Nombre de tarea": "Review meter config",
            "Cliente": "SWE",
            "Estado": "Cerrado",
            "Prioridad": "Media",
            "Responsable": "",
            "Horas": "",
            "Texto": "",
            "Tipo de tarea": "",
        })
        writer.writerow({
            "ID Tarea": "T-003",
            "Nombre de tarea": "HERON billing issue",
            "Cliente": "HERON",
            "Estado": "Analizado",
            "Prioridad": "Baja",
            "Responsable": "Ana",
            "Horas": "2",
            "Texto": "Check billing run",
            "Tipo de tarea": "Incidencia",
        })

    from src.kanban.storage.csv_import import import_tickets_from_csv

    result = import_tickets_from_csv(csv_path, data_root)

    assert result["total"] == 3
    assert result["per_client"]["SWE"] == 2
    assert result["per_client"]["HERON"] == 1

    # Verify tickets in SWE database
    swe_repo = KanbanRepository(data_root / "clients" / "SWE" / "kanban.sqlite", seed_columns=False)
    swe_tickets = swe_repo.list_tickets()
    assert len(swe_tickets) == 2

    titles = {t.title for t in swe_tickets}
    assert "Fix IDEX timeout" in titles
    assert "Review meter config" in titles

    # Verify status mapping
    idex_ticket = next(t for t in swe_tickets if t.title == "Fix IDEX timeout")
    assert idex_ticket.status == "EN_PROGRESO"
    assert idex_ticket.priority == "HIGH"
    assert idex_ticket.ticket_id == "T-001"
    assert "Check EA10" in idex_ticket.notes
    assert "Horas: 4" in idex_ticket.notes
    assert "Responsable: Juan" in idex_ticket.notes

    closed_ticket = next(t for t in swe_tickets if t.title == "Review meter config")
    assert closed_ticket.status == "CERRADO"

    # Verify HERON database
    heron_repo = KanbanRepository(data_root / "clients" / "HERON" / "kanban.sqlite", seed_columns=False)
    heron_tickets = heron_repo.list_tickets()
    assert len(heron_tickets) == 1
    assert heron_tickets[0].status == "ANALIZADO"
    assert heron_tickets[0].priority == "LOW"
