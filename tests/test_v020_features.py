"""Integration tests for v0.2.0 features + new assistant features."""
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

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


# ── Kanban: client_code in body + per-column creation ──


class TestKanbanClientCodeInBody:
    """Test that POST /api/kanban/tickets accepts client_code in body and status."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)
        # Setup TWO client directories
        from src.shared.client_manager import ClientManager
        cm = ClientManager(tmp_path)
        cm.register_client("AAA", "Client A")
        cm.register_client("BBB", "Client B")

        from src.web.app import app
        from starlette.testclient import TestClient
        c = TestClient(app)
        # Set active client to AAA
        c.post("/api/session/client", json={"code": "AAA"})
        return c

    def test_create_ticket_with_explicit_client_code(self, client):
        """Ticket created in BBB's DB even though session is AAA."""
        resp = client.post("/api/kanban/tickets", json={
            "title": "Test in BBB",
            "priority": "HIGH",
            "client_code": "BBB",
        })
        assert resp.status_code == 200
        ticket = resp.json()
        assert ticket["title"] == "Test in BBB"

        # Verify ticket is NOT in AAA's list (session client)
        resp = client.get("/api/kanban/tickets")
        data = resp.json()
        aaa_titles = [t["title"] for t in data["tickets"]]
        assert "Test in BBB" not in aaa_titles

    def test_create_ticket_falls_back_to_session_client(self, client):
        """Without client_code in body, falls back to session active client."""
        resp = client.post("/api/kanban/tickets", json={
            "title": "Test in AAA",
        })
        assert resp.status_code == 200
        resp = client.get("/api/kanban/tickets")
        assert resp.json()["total"] == 1
        assert resp.json()["tickets"][0]["title"] == "Test in AAA"

    def test_create_ticket_with_invalid_client_returns_400(self, client):
        """Non-existent client code returns 400."""
        resp = client.post("/api/kanban/tickets", json={
            "title": "Bad client",
            "client_code": "NONEXISTENT",
        })
        assert resp.status_code == 400

    def test_create_ticket_with_explicit_status(self, client):
        """Per-column creation sets status correctly."""
        resp = client.post("/api/kanban/tickets", json={
            "title": "In testing",
            "client_code": "AAA",
            "status": "TESTING",
        })
        assert resp.status_code == 200
        ticket = resp.json()
        assert ticket["status"] == "TESTING"

    def test_create_ticket_empty_status_uses_default(self, client):
        """Empty status string falls through to default (first column)."""
        resp = client.post("/api/kanban/tickets", json={
            "title": "Default status",
            "client_code": "AAA",
            "status": "",
        })
        assert resp.status_code == 200
        ticket = resp.json()
        assert ticket["status"] == "NO_ANALIZADO"


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


# ═══════════════════════════════════════════════════════════════════
#  NEW TESTS: Token gating, scope, type filter, ranking boost,
#  chat sessions, retention, search, pin, rename, export
# ═══════════════════════════════════════════════════════════════════


# ── Helpers ──

def _make_kb_item(kb_id="test-id", status="APPROVED", item_type="RESOLUTION",
                  tags=None, sap_objects=None, client_scope="standard",
                  client_code=None):
    """Create a KBItem for testing."""
    from src.assistant.storage.models import KBItem
    return KBItem(
        kb_id=kb_id, client_scope=client_scope, client_code=client_code,
        type=item_type, title=f"KB Item {kb_id}",
        content_markdown="Test content for " + kb_id,
        tags_json=json.dumps(tags or ["IDEX"]),
        sap_objects_json=json.dumps(sap_objects or ["EA02"]),
        signals_json='{}', sources_json='{}',
        version=1, status=status, content_hash="abc123",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _make_chat_service():
    """Create a ChatService with mocked dependencies."""
    from src.assistant.chat.chat_service import ChatService
    embed_svc = MagicMock()
    embed_svc.embed.return_value = [0.0] * 3072
    qdrant_svc = MagicMock()
    chat_svc = ChatService(embed_svc, qdrant_svc, api_key="fake-key")
    chat_svc.client = MagicMock()
    return chat_svc, qdrant_svc


# ── Token gating ──


class TestTokenGating:
    """Verify model_called flag and token gating."""

    def test_no_results_model_not_called(self):
        """retrieval returns 0 results -> model NOT called, model_called=False."""
        chat_svc, qdrant_svc = _make_chat_service()
        qdrant_svc.search.return_value = []
        kb_repo = MagicMock()

        result = chat_svc.answer(
            question="test question",
            kb_repo=kb_repo,
            scope="general",
            client_code=None,
        )

        assert result.model_called is False
        assert result.sources == []
        assert result.used_kb_items == []
        chat_svc.client.responses.create.assert_not_called()

    def test_results_exist_model_called(self):
        """retrieval returns >0 results -> model IS called, model_called=True."""
        chat_svc, qdrant_svc = _make_chat_service()
        item = _make_kb_item()
        qdrant_svc.search.return_value = [("test-id", 0.92)]

        kb_repo = MagicMock()
        kb_repo.get_by_id.return_value = item

        chat_svc.client.responses.create.return_value = MagicMock(
            output_text="Answer from GPT"
        )

        result = chat_svc.answer(
            question="billing error",
            kb_repo=kb_repo,
            scope="general",
            client_code=None,
        )

        assert result.model_called is True
        assert len(result.sources) == 1
        assert len(result.used_kb_items) == 1
        chat_svc.client.responses.create.assert_called_once()

    def test_qdrant_returns_ids_not_in_sqlite_treated_as_zero(self):
        """If Qdrant returns ids not found in SQLite -> treat as 0 results."""
        chat_svc, qdrant_svc = _make_chat_service()
        qdrant_svc.search.return_value = [("missing-id", 0.85)]

        kb_repo = MagicMock()
        kb_repo.get_by_id.return_value = None  # Not found in SQLite

        result = chat_svc.answer(
            question="something",
            kb_repo=kb_repo,
            scope="general",
        )

        assert result.model_called is False
        chat_svc.client.responses.create.assert_not_called()

    def test_qdrant_returns_non_approved_treated_as_zero(self):
        """If Qdrant returns ids with non-APPROVED status -> treat as 0 results."""
        chat_svc, qdrant_svc = _make_chat_service()
        item = _make_kb_item(status="DRAFT")
        qdrant_svc.search.return_value = [("test-id", 0.85)]

        kb_repo = MagicMock()
        kb_repo.get_by_id.return_value = item

        result = chat_svc.answer(
            question="something",
            kb_repo=kb_repo,
            scope="general",
        )

        assert result.model_called is False
        chat_svc.client.responses.create.assert_not_called()


# ── Scope isolation ──


class TestScopeIsolation:
    """Verify scope-aware retrieval queries correct collections."""

    def test_general_scope_queries_only_standard(self):
        """General scope queries only kb_standard."""
        chat_svc, qdrant_svc = _make_chat_service()
        qdrant_svc.search.return_value = []
        kb_repo = MagicMock()

        chat_svc.answer(
            question="test", kb_repo=kb_repo,
            scope="general", client_code=None,
        )

        call_args = qdrant_svc.search.call_args
        assert call_args.kwargs["scope"] == "general"

    def test_client_scope_queries_only_client(self):
        """Client scope queries only kb_<ACTIVE_CLIENT>."""
        chat_svc, qdrant_svc = _make_chat_service()
        qdrant_svc.search.return_value = []
        kb_repo = MagicMock()

        chat_svc.answer(
            question="test", kb_repo=kb_repo,
            scope="client", client_code="SWE",
        )

        call_args = qdrant_svc.search.call_args
        assert call_args.kwargs["scope"] == "client"
        assert call_args.kwargs["client_code"] == "SWE"

    def test_client_plus_standard_queries_both(self):
        """Client+Standard scope queries both kb_<CLIENT> and kb_standard."""
        chat_svc, qdrant_svc = _make_chat_service()
        qdrant_svc.search.return_value = []
        kb_repo = MagicMock()

        chat_svc.answer(
            question="test", kb_repo=kb_repo,
            scope="client_plus_standard", client_code="SWE",
        )

        call_args = qdrant_svc.search.call_args
        assert call_args.kwargs["scope"] == "client_plus_standard"
        assert call_args.kwargs["client_code"] == "SWE"


class TestQdrantScopeRouting:
    """Verify QdrantService routes queries to correct collections."""

    def test_general_scope_only_hits_standard(self):
        from src.assistant.retrieval.qdrant_service import QdrantService
        svc = QdrantService.__new__(QdrantService)
        svc.client = MagicMock()
        svc.VECTOR_SIZE = 3072

        svc.client.collection_exists.return_value = True
        svc.client.search.return_value = []

        svc.search(
            query_embedding=[0.0] * 3072,
            scope="general",
            client_code=None,
        )

        # Should query kb_standard only
        calls = svc.client.search.call_args_list
        collection_names = [c.kwargs["collection_name"] for c in calls]
        assert "kb_standard" in collection_names
        assert all("kb_" in cn for cn in collection_names)
        # Must NOT contain any client collection
        assert not any(cn.startswith("kb_") and cn != "kb_standard" for cn in collection_names)

    def test_client_scope_only_hits_client(self):
        from src.assistant.retrieval.qdrant_service import QdrantService
        svc = QdrantService.__new__(QdrantService)
        svc.client = MagicMock()
        svc.VECTOR_SIZE = 3072

        svc.client.collection_exists.return_value = True
        svc.client.search.return_value = []

        svc.search(
            query_embedding=[0.0] * 3072,
            scope="client",
            client_code="SWE",
        )

        calls = svc.client.search.call_args_list
        collection_names = [c.kwargs["collection_name"] for c in calls]
        assert "kb_SWE" in collection_names
        assert "kb_standard" not in collection_names

    def test_client_plus_standard_hits_both(self):
        from src.assistant.retrieval.qdrant_service import QdrantService
        svc = QdrantService.__new__(QdrantService)
        svc.client = MagicMock()
        svc.VECTOR_SIZE = 3072

        svc.client.collection_exists.return_value = True
        svc.client.search.return_value = []

        svc.search(
            query_embedding=[0.0] * 3072,
            scope="client_plus_standard",
            client_code="SWE",
        )

        calls = svc.client.search.call_args_list
        collection_names = [c.kwargs["collection_name"] for c in calls]
        assert "kb_standard" in collection_names
        assert "kb_SWE" in collection_names


# ── Type filter ──


class TestTypeFilter:
    """Verify KB type filter is passed to Qdrant and applied."""

    def test_type_filter_passed_to_qdrant(self):
        from src.assistant.retrieval.qdrant_service import QdrantService
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        svc = QdrantService.__new__(QdrantService)
        svc.client = MagicMock()
        svc.VECTOR_SIZE = 3072

        svc.client.collection_exists.return_value = True
        svc.client.search.return_value = []

        svc.search(
            query_embedding=[0.0] * 3072,
            scope="general",
            type_filter="INCIDENT_PATTERN",
        )

        call_args = svc.client.search.call_args
        qf = call_args.kwargs["query_filter"]
        assert qf is not None
        assert qf.must[0].key == "type"
        assert qf.must[0].match.value == "INCIDENT_PATTERN"

    def test_no_type_filter_sends_none(self):
        from src.assistant.retrieval.qdrant_service import QdrantService

        svc = QdrantService.__new__(QdrantService)
        svc.client = MagicMock()
        svc.VECTOR_SIZE = 3072

        svc.client.collection_exists.return_value = True
        svc.client.search.return_value = []

        svc.search(
            query_embedding=[0.0] * 3072,
            scope="general",
            type_filter=None,
        )

        call_args = svc.client.search.call_args
        assert call_args.kwargs["query_filter"] is None

    def test_type_filter_in_chat_service(self):
        """Type filter flows through ChatService to QdrantService."""
        chat_svc, qdrant_svc = _make_chat_service()
        qdrant_svc.search.return_value = []
        kb_repo = MagicMock()

        chat_svc.answer(
            question="test", kb_repo=kb_repo,
            scope="general", type_filter="ROOT_CAUSE",
        )

        call_args = qdrant_svc.search.call_args
        assert call_args.kwargs["type_filter"] == "ROOT_CAUSE"


# ── Ranking boost ──


class TestRankingBoost:
    """Verify deterministic ranking boost by tags and sap_objects."""

    def test_matching_tags_boost_ranking(self):
        """Items with matching tags should rank higher."""
        chat_svc, qdrant_svc = _make_chat_service()

        item_low = _make_kb_item(kb_id="low", tags=["UNRELATED"], sap_objects=[])
        item_high = _make_kb_item(kb_id="high", tags=["IDEX", "UTILMD"], sap_objects=[])

        # Qdrant returns items with same base score
        qdrant_svc.search.return_value = [("low", 0.80), ("high", 0.80)]

        kb_repo = MagicMock()
        kb_repo.get_by_id.side_effect = lambda kid: item_low if kid == "low" else item_high

        chat_svc.client.responses.create.return_value = MagicMock(output_text="answer")

        # Query mentions IDEX - should boost the "high" item
        result = chat_svc.answer(
            question="Tell me about IDEX process",
            kb_repo=kb_repo, scope="general",
        )

        # The item with matching tags (IDEX) should be first in sources
        assert result.sources[0].kb_id == "high"

    def test_matching_sap_objects_boost_ranking(self):
        """Items with matching sap_objects should rank higher."""
        chat_svc, qdrant_svc = _make_chat_service()

        item_a = _make_kb_item(kb_id="a", tags=[], sap_objects=["EA02"])
        item_b = _make_kb_item(kb_id="b", tags=[], sap_objects=["/IDXGC/PDOCMON01"])

        qdrant_svc.search.return_value = [("a", 0.80), ("b", 0.80)]
        kb_repo = MagicMock()
        kb_repo.get_by_id.side_effect = lambda kid: item_a if kid == "a" else item_b

        chat_svc.client.responses.create.return_value = MagicMock(output_text="answer")

        # Query mentions /IDXGC/PDOCMON01
        result = chat_svc.answer(
            question="Check /IDXGC/PDOCMON01 program",
            kb_repo=kb_repo, scope="general",
        )

        assert result.sources[0].kb_id == "b"

    def test_boost_is_deterministic(self):
        """Same input always produces same ranking."""
        from src.assistant.chat.chat_service import ChatService

        chat_svc, qdrant_svc = _make_chat_service()
        item_a = _make_kb_item(kb_id="a", tags=["GPKE"], sap_objects=[])
        item_b = _make_kb_item(kb_id="b", tags=["UTILMD"], sap_objects=[])

        kb_repo = MagicMock()
        kb_repo.get_by_id.side_effect = lambda kid: item_a if kid == "a" else item_b

        results = chat_svc._fetch_and_boost(
            [("a", 0.80), ("b", 0.80)], kb_repo, "Something about GPKE"
        )
        first_run = [item.kb_id for item, _ in results]

        results2 = chat_svc._fetch_and_boost(
            [("a", 0.80), ("b", 0.80)], kb_repo, "Something about GPKE"
        )
        second_run = [item.kb_id for item, _ in results2]

        assert first_run == second_run


# ── Chat sessions (repository level) ──


class TestChatSessions:
    """Chat session and message persistence."""

    def test_create_session(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")
        session = repo.create_session(scope="general", title="Test Chat")

        assert session.session_id
        assert session.scope == "general"
        assert session.title == "Test Chat"
        assert session.is_pinned == 0

    def test_create_and_get_session(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")
        session = repo.create_session(scope="client", client_code="SWE", title="SWE Chat")

        retrieved = repo.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.scope == "client"
        assert retrieved.client_code == "SWE"
        assert retrieved.title == "SWE Chat"

    def test_add_and_get_messages(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")
        session = repo.create_session(scope="general")

        repo.add_message(session.session_id, "user", "Hello")
        repo.add_message(session.session_id, "assistant", "Hi there",
                         used_kb_items_json='[{"kb_id": "x"}]', model_called=1)

        messages = repo.get_messages(session.session_id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"
        assert messages[1].role == "assistant"
        assert messages[1].model_called == 1
        assert json.loads(messages[1].used_kb_items_json) == [{"kb_id": "x"}]

    def test_list_sessions_ordered_by_activity(self, tmp_path):
        import time
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        s1 = repo.create_session(scope="general", title="Old Chat")
        time.sleep(0.01)
        s2 = repo.create_session(scope="general", title="New Chat")

        sessions = repo.list_sessions()
        assert sessions[0].title == "New Chat"
        assert sessions[1].title == "Old Chat"

    def test_switching_sessions_loads_correct_messages(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        s1 = repo.create_session(scope="general", title="Session A")
        s2 = repo.create_session(scope="general", title="Session B")

        repo.add_message(s1.session_id, "user", "Msg in A")
        repo.add_message(s2.session_id, "user", "Msg in B")

        msgs_a = repo.get_messages(s1.session_id)
        msgs_b = repo.get_messages(s2.session_id)

        assert len(msgs_a) == 1
        assert msgs_a[0].content == "Msg in A"
        assert len(msgs_b) == 1
        assert msgs_b[0].content == "Msg in B"


# ── Retention ──


class TestRetention:
    """Retention deletes unpinned old sessions and cascades messages."""

    def test_deletes_old_unpinned_sessions(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        # Create an old session by manipulating the DB directly
        session = repo.create_session(scope="general", title="Old Session")
        old_date = (datetime.now(UTC) - timedelta(days=40)).isoformat()
        with sqlite3.connect(tmp_path / "chat.db") as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "UPDATE chat_sessions SET last_message_at = ? WHERE session_id = ?",
                (old_date, session.session_id),
            )
            conn.commit()

        deleted = repo.cleanup_retention(30)
        assert deleted == 1
        assert repo.get_session(session.session_id) is None

    def test_pinned_sessions_survive_cleanup(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        session = repo.create_session(scope="general", title="Pinned Old")
        repo.pin_session(session.session_id, True)

        # Make it old
        old_date = (datetime.now(UTC) - timedelta(days=40)).isoformat()
        with sqlite3.connect(tmp_path / "chat.db") as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "UPDATE chat_sessions SET last_message_at = ? WHERE session_id = ?",
                (old_date, session.session_id),
            )
            conn.commit()

        deleted = repo.cleanup_retention(30)
        assert deleted == 0
        assert repo.get_session(session.session_id) is not None

    def test_cascade_deletes_messages(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        session = repo.create_session(scope="general", title="Old")
        repo.add_message(session.session_id, "user", "Hello")
        repo.add_message(session.session_id, "assistant", "Hi")

        old_date = (datetime.now(UTC) - timedelta(days=40)).isoformat()
        with sqlite3.connect(tmp_path / "chat.db") as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "UPDATE chat_sessions SET last_message_at = ? WHERE session_id = ?",
                (old_date, session.session_id),
            )
            conn.commit()

        repo.cleanup_retention(30)

        # Messages should be gone too
        messages = repo.get_messages(session.session_id)
        assert len(messages) == 0


# ── History search ──


class TestHistorySearch:
    """Search filters sessions by title and/or contents."""

    def test_search_by_title(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        repo.create_session(scope="general", title="Billing Error Fix")
        repo.create_session(scope="general", title="IDEX Process")

        results = repo.search_sessions("Billing")
        assert len(results) == 1
        assert results[0].title == "Billing Error Fix"

    def test_search_by_message_content(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        s1 = repo.create_session(scope="general", title="Chat A")
        s2 = repo.create_session(scope="general", title="Chat B")
        repo.add_message(s1.session_id, "user", "How to fix EA02 error?")
        repo.add_message(s2.session_id, "user", "What is GPKE?")

        results = repo.search_sessions("EA02")
        assert len(results) == 1
        assert results[0].title == "Chat A"


# ── Rename ──


class TestRenameSession:
    """Renamed title persists and is shown after reload."""

    def test_rename_persists(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        session = repo.create_session(scope="general", title="Old Title")
        renamed = repo.rename_session(session.session_id, "New Title")

        assert renamed.title == "New Title"

        # Reload from DB
        reloaded = repo.get_session(session.session_id)
        assert reloaded.title == "New Title"


# ── Export ──


class TestExportSession:
    """MD and JSON export with correct content and format."""

    def test_export_markdown(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        session = repo.create_session(scope="client", client_code="SWE", title="Export Test")
        repo.add_message(session.session_id, "user", "What is EA02?")
        repo.add_message(session.session_id, "assistant", "EA02 is a transaction.",
                         used_kb_items_json='[{"kb_id": "abc"}]', model_called=1)

        md = repo.export_session_markdown(session.session_id)
        assert md is not None
        assert "# Export Test" in md
        assert "What is EA02?" in md
        assert "EA02 is a transaction." in md
        assert "Model called: Yes" in md
        assert "SWE" in md

    def test_export_json(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        session = repo.create_session(scope="general", title="JSON Export")
        repo.add_message(session.session_id, "user", "Hello")
        repo.add_message(session.session_id, "assistant", "Hi",
                         model_called=0)

        raw = repo.export_session_json(session.session_id)
        assert raw is not None
        data = json.loads(raw)
        assert data["title"] == "JSON Export"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["model_called"] is False

    def test_export_nonexistent_returns_none(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")
        assert repo.export_session_markdown("fake-id") is None
        assert repo.export_session_json("fake-id") is None


# ═══════════════════════════════════════════════════════════════════
#  E2E TESTS (service-level end-to-end)
# ═══════════════════════════════════════════════════════════════════


class TestE2E1ClientScopeResultsExist:
    """E2E-1: Client scope, results exist."""

    def test_client_scope_with_approved_kb_item(self, tmp_path):
        from src.assistant.chat.chat_service import ChatService
        from src.assistant.storage.kb_repository import KBItemRepository
        from src.assistant.storage.models import KBItemType, KBItemStatus
        from src.assistant.storage.chat_repository import ChatRepository

        # Create approved KB item for client
        kb_repo = KBItemRepository(tmp_path / "assistant_kb.sqlite")
        item, _ = kb_repo.create_or_update(
            client_scope="client", client_code="SWE",
            item_type=KBItemType.RESOLUTION, title="Fix billing EA02",
            content_markdown="Steps: 1. Open EA02...",
            tags=["billing"], sap_objects=["EA02"],
            signals={}, sources={}, status=KBItemStatus.APPROVED,
        )

        # Setup mocked services
        embed_svc = MagicMock()
        embed_svc.embed.return_value = [0.0] * 3072

        qdrant_svc = MagicMock()
        qdrant_svc.search.return_value = [(item.kb_id, 0.90)]

        chat_svc = ChatService(embed_svc, qdrant_svc, api_key="fake")
        chat_svc.client = MagicMock()
        chat_svc.client.responses.create.return_value = MagicMock(
            output_text="To fix billing, open EA02..."
        )

        # Query in client scope
        result = chat_svc.answer(
            question="How to fix billing?",
            kb_repo=kb_repo,
            scope="client",
            client_code="SWE",
        )

        # Verify retrieval occurred in client scope
        qdrant_svc.search.assert_called_once()
        assert qdrant_svc.search.call_args.kwargs["scope"] == "client"

        # Verify model was called
        assert result.model_called is True
        chat_svc.client.responses.create.assert_called_once()

        # Verify response and sources saved
        assert "EA02" in result.answer
        assert len(result.sources) == 1
        assert len(result.used_kb_items) == 1
        assert result.used_kb_items[0]["kb_id"] == item.kb_id

        # Persist to chat session
        chat_repo = ChatRepository(tmp_path / "chat.db")
        session = chat_repo.create_session(scope="client", client_code="SWE")
        chat_repo.add_message(session.session_id, "user", "How to fix billing?")
        chat_repo.add_message(
            session.session_id, "assistant", result.answer,
            used_kb_items_json=json.dumps(result.used_kb_items),
            model_called=1,
        )

        msgs = chat_repo.get_messages(session.session_id)
        assert len(msgs) == 2
        assert msgs[1].model_called == 1


class TestE2E2ClientScopeNoResults:
    """E2E-2: Client scope, no results."""

    def test_no_kb_items_model_not_called(self, tmp_path):
        from src.assistant.chat.chat_service import ChatService
        from src.assistant.storage.kb_repository import KBItemRepository
        from src.assistant.storage.chat_repository import ChatRepository

        kb_repo = KBItemRepository(tmp_path / "assistant_kb.sqlite")

        embed_svc = MagicMock()
        embed_svc.embed.return_value = [0.0] * 3072
        qdrant_svc = MagicMock()
        qdrant_svc.search.return_value = []

        chat_svc = ChatService(embed_svc, qdrant_svc, api_key="fake")
        chat_svc.client = MagicMock()

        result = chat_svc.answer(
            question="Anything",
            kb_repo=kb_repo,
            scope="client",
            client_code="SWE",
        )

        # Model not called
        assert result.model_called is False
        chat_svc.client.responses.create.assert_not_called()
        # No knowledge found message
        assert "No se encontraron" in result.answer

        # Persist
        chat_repo = ChatRepository(tmp_path / "chat.db")
        session = chat_repo.create_session(scope="client", client_code="SWE")
        chat_repo.add_message(session.session_id, "assistant", result.answer, model_called=0)

        msgs = chat_repo.get_messages(session.session_id)
        assert msgs[0].model_called == 0


class TestE2E3ClientPlusStandardMerge:
    """E2E-3: Client+Standard merge."""

    def test_merged_results_from_both_collections(self, tmp_path):
        from src.assistant.chat.chat_service import ChatService
        from src.assistant.storage.kb_repository import KBItemRepository
        from src.assistant.storage.models import KBItemType, KBItemStatus

        # Create one KB in standard and one in client
        kb_repo = KBItemRepository(tmp_path / "assistant_kb.sqlite")
        std_item, _ = kb_repo.create_or_update(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY, title="GPKE Protocol",
            content_markdown="GPKE is...", tags=["GPKE"], sap_objects=[],
            signals={}, sources={}, status=KBItemStatus.APPROVED,
        )
        client_item, _ = kb_repo.create_or_update(
            client_scope="client", client_code="SWE",
            item_type=KBItemType.RESOLUTION, title="SWE Billing Fix",
            content_markdown="Fix steps...", tags=["billing"], sap_objects=["EA02"],
            signals={}, sources={}, status=KBItemStatus.APPROVED,
        )

        embed_svc = MagicMock()
        embed_svc.embed.return_value = [0.0] * 3072

        qdrant_svc = MagicMock()
        # Both collections return results
        qdrant_svc.search.return_value = [
            (std_item.kb_id, 0.85),
            (client_item.kb_id, 0.90),
        ]

        chat_svc = ChatService(embed_svc, qdrant_svc, api_key="fake")
        chat_svc.client = MagicMock()
        chat_svc.client.responses.create.return_value = MagicMock(
            output_text="Based on GPKE and SWE billing..."
        )

        result = chat_svc.answer(
            question="Tell me about billing and GPKE",
            kb_repo=kb_repo,
            scope="client_plus_standard",
            client_code="SWE",
        )

        # Verify merged results
        assert result.model_called is True
        assert len(result.sources) == 2
        # Client item should rank higher (higher base score + possible boost)
        source_ids = [s.kb_id for s in result.sources]
        assert std_item.kb_id in source_ids
        assert client_item.kb_id in source_ids


class TestE2E4ChatHistory:
    """E2E-4: Chat history - create sessions, switch between them."""

    def test_create_and_switch_sessions(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        # Create chat A with messages
        s_a = repo.create_session(scope="general", title="Chat A")
        repo.add_message(s_a.session_id, "user", "Question A")
        repo.add_message(s_a.session_id, "assistant", "Answer A", model_called=1)

        # New chat creates chat B
        s_b = repo.create_session(scope="client", client_code="SWE", title="Chat B")
        repo.add_message(s_b.session_id, "user", "Question B")

        # Verify sidebar shows both
        sessions = repo.list_sessions()
        assert len(sessions) == 2

        # Switching works
        msgs_a = repo.get_messages(s_a.session_id)
        msgs_b = repo.get_messages(s_b.session_id)
        assert len(msgs_a) == 2
        assert msgs_a[0].content == "Question A"
        assert len(msgs_b) == 1
        assert msgs_b[0].content == "Question B"


class TestE2E5RetentionAndPin:
    """E2E-5: Retention + pin."""

    def test_pinned_survives_unpinned_deleted(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        # Create old sessions
        pinned = repo.create_session(scope="general", title="Pinned")
        repo.pin_session(pinned.session_id, True)

        unpinned = repo.create_session(scope="general", title="Unpinned")

        # Make both old
        old_date = (datetime.now(UTC) - timedelta(days=40)).isoformat()
        with sqlite3.connect(tmp_path / "chat.db") as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "UPDATE chat_sessions SET last_message_at = ? WHERE session_id = ?",
                (old_date, pinned.session_id),
            )
            conn.execute(
                "UPDATE chat_sessions SET last_message_at = ? WHERE session_id = ?",
                (old_date, unpinned.session_id),
            )
            conn.commit()

        deleted = repo.cleanup_retention(30)
        assert deleted == 1

        # Pinned must remain
        assert repo.get_session(pinned.session_id) is not None
        # Unpinned must be deleted
        assert repo.get_session(unpinned.session_id) is None


class TestE2E6RenameAndExport:
    """E2E-6: Rename + export."""

    def test_rename_then_export(self, tmp_path):
        from src.assistant.storage.chat_repository import ChatRepository
        repo = ChatRepository(tmp_path / "chat.db")

        session = repo.create_session(scope="general", title="Original")
        repo.add_message(session.session_id, "user", "Hello world")
        repo.add_message(session.session_id, "assistant", "Hi!", model_called=1)

        # Rename
        repo.rename_session(session.session_id, "Renamed Session")

        # Export MD
        md = repo.export_session_markdown(session.session_id)
        assert "# Renamed Session" in md
        assert "Hello world" in md
        assert "Hi!" in md

        # Export JSON
        raw_json = repo.export_session_json(session.session_id)
        data = json.loads(raw_json)
        assert data["title"] == "Renamed Session"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["content"] == "Hello world"
        assert data["messages"][1]["content"] == "Hi!"
        assert data["messages"][1]["model_called"] is True


# ── Chat Session API tests ──


class TestChatSessionAPI:
    """API-level tests for session management endpoints."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.shared.client_manager import ClientManager
        cm = ClientManager(tmp_path)
        cm.register_client("TST", "Test Client")

        from src.web.app import app
        from starlette.testclient import TestClient
        c = TestClient(app)
        c.post("/api/session/client", json={"code": "TST"})
        return c

    def test_create_and_list_sessions(self, client):
        resp = client.post("/api/chat/sessions", json={"scope": "general", "title": "My Chat"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "My Chat"
        assert data["scope"] == "general"

        resp = client.get("/api/chat/sessions")
        sessions = resp.json()
        assert len(sessions) >= 1
        assert any(s["title"] == "My Chat" for s in sessions)

    def test_get_messages(self, client):
        resp = client.post("/api/chat/sessions", json={"scope": "general"})
        sid = resp.json()["session_id"]

        resp = client.get(f"/api/chat/sessions/{sid}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_rename_session(self, client):
        resp = client.post("/api/chat/sessions", json={"scope": "general", "title": "Old"})
        sid = resp.json()["session_id"]

        resp = client.put(f"/api/chat/sessions/{sid}/rename", json={"title": "New"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "New"

    def test_pin_unpin_session(self, client):
        resp = client.post("/api/chat/sessions", json={"scope": "general"})
        sid = resp.json()["session_id"]

        resp = client.put(f"/api/chat/sessions/{sid}/pin", json={"pinned": True})
        assert resp.status_code == 200
        assert resp.json()["is_pinned"] == 1

        resp = client.put(f"/api/chat/sessions/{sid}/pin", json={"pinned": False})
        assert resp.json()["is_pinned"] == 0

    def test_delete_session(self, client):
        resp = client.post("/api/chat/sessions", json={"scope": "general"})
        sid = resp.json()["session_id"]

        resp = client.delete(f"/api/chat/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        resp = client.delete(f"/api/chat/sessions/{sid}")
        assert resp.status_code == 404

    def test_export_json(self, client):
        resp = client.post("/api/chat/sessions", json={"scope": "general", "title": "Export Me"})
        sid = resp.json()["session_id"]

        resp = client.get(f"/api/chat/sessions/{sid}/export?format=json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        data = json.loads(resp.text)
        assert data["title"] == "Export Me"

    def test_export_md(self, client):
        resp = client.post("/api/chat/sessions", json={"scope": "general", "title": "MD Export"})
        sid = resp.json()["session_id"]

        resp = client.get(f"/api/chat/sessions/{sid}/export?format=md")
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        assert "# MD Export" in resp.text

    def test_search_sessions_api(self, client):
        client.post("/api/chat/sessions", json={"scope": "general", "title": "Alpha Session"})
        client.post("/api/chat/sessions", json={"scope": "general", "title": "Beta Session"})

        resp = client.get("/api/chat/sessions?search=Alpha")
        sessions = resp.json()
        assert len(sessions) == 1
        assert sessions[0]["title"] == "Alpha Session"

    def test_retention_api(self, client):
        resp = client.post("/api/chat/retention", json={"days": 30})
        assert resp.status_code == 200
        data = resp.json()
        assert data["chat_retention_days"] == 30

    def test_retention_invalid_days(self, client):
        resp = client.post("/api/chat/retention", json={"days": 10})
        assert resp.status_code == 400
