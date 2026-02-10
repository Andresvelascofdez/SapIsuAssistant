"""Integration tests for v0.2.0 features."""
import json
import sqlite3
from pathlib import Path

import pytest

from src.kanban.storage.kanban_repository import KanbanRepository, TicketPriority


# ── Repository: delete_ticket ──


class TestDeleteTicket:
    def test_delete_existing_ticket(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="To delete", priority="HIGH")
        assert repo.get_by_id(t.id) is not None
        assert repo.delete_ticket(t.id) is True
        assert repo.get_by_id(t.id) is None

    def test_delete_removes_history(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Has history")
        repo.update_status(t.id, "TESTING")
        assert len(repo.get_history(t.id)) == 2
        repo.delete_ticket(t.id)
        assert len(repo.get_history(t.id)) == 0

    def test_delete_nonexistent_returns_false(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        assert repo.delete_ticket("nonexistent-id") is False


# ── Repository: search ──


class TestSearchTickets:
    def test_search_by_ticket_id(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="Alpha", ticket_id="SWE-001")
        repo.create_ticket(title="Beta", ticket_id="SWE-002")
        repo.create_ticket(title="Gamma", ticket_id="HER-001")
        results = repo.list_tickets(search="SWE")
        assert len(results) == 2

    def test_search_by_title(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="Fix login bug")
        repo.create_ticket(title="Add feature")
        results = repo.list_tickets(search="login")
        assert len(results) == 1
        assert results[0].title == "Fix login bug"

    def test_search_by_notes(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="T1", notes="Contains keyword xyz")
        repo.create_ticket(title="T2", notes="Nothing here")
        results = repo.list_tickets(search="xyz")
        assert len(results) == 1

    def test_search_case_insensitive(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="ImportantTask", ticket_id="ABC-123")
        results = repo.list_tickets(search="abc")
        assert len(results) == 1


# ── Repository: filter by priority ──


class TestFilterByPriority:
    def test_filter_high(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="Low prio", priority="LOW")
        repo.create_ticket(title="High prio", priority="HIGH")
        repo.create_ticket(title="High prio 2", priority="HIGH")
        results = repo.list_tickets(priority="HIGH")
        assert len(results) == 2

    def test_combined_search_and_priority(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="Bug A", priority="HIGH", ticket_id="BUG-1")
        repo.create_ticket(title="Bug B", priority="LOW", ticket_id="BUG-2")
        repo.create_ticket(title="Feature", priority="HIGH", ticket_id="FEAT-1")
        results = repo.list_tickets(search="BUG", priority="HIGH")
        assert len(results) == 1
        assert results[0].ticket_id == "BUG-1"


# ── Repository: pagination ──


class TestPagination:
    def test_limit(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        for i in range(10):
            repo.create_ticket(title=f"Ticket {i}")
        results = repo.list_tickets(limit=3)
        assert len(results) == 3

    def test_limit_and_offset(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        for i in range(10):
            repo.create_ticket(title=f"Ticket {i}")
        page1 = repo.list_tickets(limit=5, offset=0)
        page2 = repo.list_tickets(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        all_ids = {t.id for t in page1} | {t.id for t in page2}
        assert len(all_ids) == 10

    def test_count_tickets(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        for i in range(7):
            repo.create_ticket(title=f"Ticket {i}", priority="HIGH" if i < 3 else "LOW")
        assert repo.count_tickets() == 7
        assert repo.count_tickets(priority="HIGH") == 3


# ── Repository: update with tags and links ──


class TestUpdateTagsLinks:
    def test_update_tags(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Test", tags=["old"])
        updated = repo.update_ticket(t.id, tags=["new", "tags"])
        assert json.loads(updated.tags_json) == ["new", "tags"]

    def test_update_links(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Test", links=[])
        updated = repo.update_ticket(t.id, links=["https://example.com"])
        assert json.loads(updated.links_json) == ["https://example.com"]


# ── Column management ──


class TestColumns:
    def test_default_8_columns(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        cols = repo.list_columns()
        assert len(cols) == 8
        assert cols[0].name == "NO_ANALIZADO"
        assert cols[7].name == "CERRADO"

    def test_create_column(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        col = repo.create_column("CUSTOM", "Custom Status")
        assert col.name == "CUSTOM"
        assert col.position == 8
        assert len(repo.list_columns()) == 9

    def test_rename_column(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        cols = repo.list_columns()
        renamed = repo.rename_column(cols[0].id, "Nuevo nombre")
        assert renamed.display_name == "Nuevo nombre"

    def test_delete_empty_column(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        col = repo.create_column("TEMP", "Temporary")
        assert repo.delete_column(col.id) is True
        assert len(repo.list_columns()) == 8

    def test_delete_column_with_tickets_raises(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="Ticket in NA", status="NO_ANALIZADO")
        cols = repo.list_columns()
        na_col = next(c for c in cols if c.name == "NO_ANALIZADO")
        with pytest.raises(ValueError):
            repo.delete_column(na_col.id)

    def test_reorder_columns(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        cols = repo.list_columns()
        reversed_ids = [c.id for c in reversed(cols)]
        reordered = repo.reorder_columns(reversed_ids)
        assert reordered[0].name == "CERRADO"
        assert reordered[-1].name == "NO_ANALIZADO"


# ── Web API (via httpx) ──


class TestKanbanAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        # Patch DATA_ROOT at module level so it takes effect
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)
        # Setup client directory
        client_dir = tmp_path / "clients" / "TST"
        client_dir.mkdir(parents=True)
        # Register client
        from src.shared.client_manager import ClientManager
        cm = ClientManager(tmp_path)
        cm.register_client("TST", "Test Client")

        from src.web.app import app
        from starlette.testclient import TestClient
        c = TestClient(app)
        # Set active client
        c.post("/api/session/client", json={"code": "TST"})
        return c

    def test_list_tickets_returns_dict(self, client):
        resp = client.get("/api/kanban/tickets")
        assert resp.status_code == 200
        data = resp.json()
        assert "tickets" in data
        assert "total" in data

    def test_create_and_list_ticket(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "Test Ticket", "priority": "HIGH"})
        assert resp.status_code == 200
        ticket = resp.json()
        assert ticket["title"] == "Test Ticket"
        assert ticket["priority"] == "HIGH"
        assert "links" in ticket

        resp = client.get("/api/kanban/tickets")
        data = resp.json()
        assert data["total"] == 1

    def test_delete_ticket(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "Delete Me"})
        ticket_id = resp.json()["id"]
        resp = client.delete(f"/api/kanban/tickets/{ticket_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        resp = client.get("/api/kanban/tickets")
        assert resp.json()["total"] == 0

    def test_delete_nonexistent_ticket(self, client):
        resp = client.delete("/api/kanban/tickets/fake-id")
        assert resp.status_code == 404

    def test_update_ticket_with_tags_links(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "Tagged"})
        tid = resp.json()["id"]
        resp = client.put(f"/api/kanban/tickets/{tid}", json={
            "tags": ["bug", "p1"],
            "links": ["https://jira.example.com/1"],
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["tags"] == ["bug", "p1"]
        assert updated["links"] == ["https://jira.example.com/1"]

    def test_search_server_side(self, client):
        client.post("/api/kanban/tickets", json={"title": "Alpha task"})
        client.post("/api/kanban/tickets", json={"title": "Beta bug"})
        resp = client.get("/api/kanban/tickets?search=alpha")
        data = resp.json()
        assert data["total"] == 1
        assert data["tickets"][0]["title"] == "Alpha task"

    def test_filter_priority(self, client):
        client.post("/api/kanban/tickets", json={"title": "Low", "priority": "LOW"})
        client.post("/api/kanban/tickets", json={"title": "Critical", "priority": "CRITICAL"})
        resp = client.get("/api/kanban/tickets?priority=CRITICAL")
        data = resp.json()
        assert data["total"] == 1
        assert data["tickets"][0]["priority"] == "CRITICAL"

    def test_export_csv(self, client):
        client.post("/api/kanban/tickets", json={"title": "Export me"})
        resp = client.get("/api/kanban/export-csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        content = resp.text
        assert "Export me" in content
        assert "ID Tarea" in content

    def test_columns_default_8(self, client):
        resp = client.get("/api/kanban/columns")
        cols = resp.json()
        assert len(cols) == 8
        assert cols[0]["name"] == "NO_ANALIZADO"

    def test_ticket_history(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "Track me"})
        tid = resp.json()["id"]
        client.put(f"/api/kanban/tickets/{tid}/move", json={"status": "TESTING"})
        resp = client.get(f"/api/kanban/tickets/{tid}/history")
        history = resp.json()
        assert len(history) == 2
        assert history[1]["to_status"] == "TESTING"


# ── Session persistence ──


class TestSessionPersistence:
    def test_session_key_file_created(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        monkeypatch.delenv("SESSION_SECRET", raising=False)

        # Re-import to trigger key generation
        import importlib
        import src.web.app as app_mod
        app_mod._DATA_ROOT = tmp_path
        key = app_mod._get_session_secret()
        assert len(key) == 64  # hex(32 bytes)
        key_file = tmp_path / ".session_key"
        assert key_file.exists()
        # Same key on second call
        assert app_mod._get_session_secret() == key
