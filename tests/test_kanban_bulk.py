"""Bulk Kanban ticket operations."""
import sqlite3

from src.kanban.storage.kanban_repository import KanbanRepository
from src.shared.client_manager import ClientManager


def _make_client(tmp_path, monkeypatch, clients=("TST",), active_client="TST"):
    monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
    import src.web.dependencies as deps

    monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)
    cm = ClientManager(tmp_path)
    for code in clients:
        cm.register_client(code, f"{code} Client")

    from src.web.app import app
    from starlette.testclient import TestClient

    client = TestClient(app)
    if active_client:
        client.post("/api/session/client", json={"code": active_client})
    return client


class TestKanbanBulkRepository:
    def test_close_all_and_delete_closed(self, tmp_path):
        repo = KanbanRepository(tmp_path / "kanban.sqlite", seed_columns=True)
        open_ticket = repo.create_ticket(title="Open", status="EN_PROGRESO")
        testing_ticket = repo.create_ticket(title="Testing", status="TESTING")
        already_closed = repo.create_ticket(title="Closed", status="CERRADO")

        closed_count = repo.close_all_tickets()
        assert closed_count == 2
        assert repo.get_by_id(open_ticket.id).status == "CERRADO"
        assert repo.get_by_id(testing_ticket.id).closed_at is not None
        assert repo.get_by_id(already_closed.id).status == "CERRADO"
        assert len(repo.get_history(open_ticket.id)) == 2

        deleted_count = repo.delete_closed_tickets()
        assert deleted_count == 3
        assert repo.list_tickets() == []

        with sqlite3.connect(tmp_path / "kanban.sqlite") as conn:
            assert conn.execute("SELECT COUNT(*) FROM ticket_history").fetchone()[0] == 0


class TestKanbanBulkAPI:
    def test_bulk_close_and_delete_active_client(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        t1 = client.post("/api/kanban/tickets", json={"client_code": "TST", "title": "One"}).json()
        t2 = client.post("/api/kanban/tickets", json={"client_code": "TST", "title": "Two"}).json()

        resp = client.post("/api/kanban/tickets/bulk-close", json={"client_code": "TST"})
        assert resp.status_code == 200
        assert resp.json()["closed"] == 2

        tickets = client.get("/api/kanban/tickets").json()["tickets"]
        assert {ticket["id"]: ticket["status"] for ticket in tickets} == {
            t1["id"]: "CERRADO",
            t2["id"]: "CERRADO",
        }

        resp = client.delete("/api/kanban/tickets/closed?client_code=TST")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2
        assert client.get("/api/kanban/tickets").json()["total"] == 0

    def test_bulk_close_without_active_client_applies_all_clients(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch, clients=("AAA", "BBB"), active_client=None)
        client.post("/api/kanban/tickets", json={"client_code": "AAA", "title": "A"})
        client.post("/api/kanban/tickets", json={"client_code": "BBB", "title": "B"})

        resp = client.post("/api/kanban/tickets/bulk-close", json={})
        assert resp.status_code == 200
        assert resp.json()["closed"] == 2
        assert resp.json()["per_client"] == {"AAA": 1, "BBB": 1}

        resp = client.delete("/api/kanban/tickets/closed")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2
        assert client.get("/api/kanban/tickets").json()["total"] == 0
