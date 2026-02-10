"""
Tests for web routes and FastAPI application.

Uses FastAPI TestClient to validate all API endpoints without starting a server.
All tests use tmp_path for data isolation.
"""
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock, AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _use_tmp_data(tmp_path, monkeypatch):
    """Route all data to tmp_path for test isolation."""
    monkeypatch.setattr("src.web.dependencies.DATA_ROOT", tmp_path)
    (tmp_path / "standard").mkdir(parents=True, exist_ok=True)


@pytest.fixture()
def client():
    from src.web.app import app
    with TestClient(app) as c:
        yield c


# ───────── App / Root ─────────


class TestAppRoot:
    def test_root_redirects_to_chat(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "/chat"

    def test_static_css_served(self, client):
        resp = client.get("/static/style.css")
        assert resp.status_code == 200

    def test_openapi_available(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["info"]["title"] == "SAP IS-U Assistant"


# ───────── AppState / Dependencies ─────────


class TestAppState:
    def test_app_state_dataclass(self):
        from src.shared.app_state import AppState
        state = AppState(data_root=Path("/tmp/test"))
        assert state.data_root == Path("/tmp/test")
        assert state.active_client_code is None
        assert state.standard_kb_enabled is True
        assert state.qdrant_url == "http://localhost:6333"

    def test_app_state_mutable(self):
        from src.shared.app_state import AppState
        state = AppState(data_root=Path("/tmp/test"))
        state.active_client_code = "SWE"
        assert state.active_client_code == "SWE"
        state.standard_kb_enabled = False
        assert state.standard_kb_enabled is False


# ───────── Page Rendering ─────────


class TestPageRendering:
    def test_chat_page(self, client):
        resp = client.get("/chat")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_kanban_page(self, client):
        resp = client.get("/kanban")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_review_page(self, client):
        resp = client.get("/review")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_ingest_page(self, client):
        resp = client.get("/ingest")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_settings_page(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


# ───────── Settings API ─────────


class TestSettingsAPI:
    def test_register_client(self, client):
        resp = client.post("/api/settings/client", json={"code": "TST", "name": "Test Client"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "TST"
        assert data["name"] == "Test Client"

    def test_register_client_missing_code(self, client):
        resp = client.post("/api/settings/client", json={"code": "", "name": "X"})
        assert resp.status_code == 400

    def test_register_client_missing_name(self, client):
        resp = client.post("/api/settings/client", json={"code": "X", "name": ""})
        assert resp.status_code == 400

    def test_register_duplicate_client(self, client):
        client.post("/api/settings/client", json={"code": "DUP", "name": "First"})
        resp = client.post("/api/settings/client", json={"code": "DUP", "name": "Second"})
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_list_clients_empty(self, client):
        resp = client.get("/api/settings/clients")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_clients_after_register(self, client):
        client.post("/api/settings/client", json={"code": "ABC", "name": "ABC Corp"})
        resp = client.get("/api/settings/clients")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["code"] == "ABC"

    def test_set_qdrant_url(self, client):
        resp = client.post("/api/settings/qdrant", json={"url": "http://my-qdrant:6333"})
        assert resp.status_code == 200
        assert resp.json()["qdrant_url"] == "http://my-qdrant:6333"

    def test_set_qdrant_url_empty(self, client):
        resp = client.post("/api/settings/qdrant", json={"url": ""})
        assert resp.status_code == 400

    def test_set_api_key(self, client, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        resp = client.post("/api/settings/apikey", json={"key": "sk-test-key"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert os.environ.get("OPENAI_API_KEY") == "sk-test-key"

    def test_set_api_key_empty(self, client):
        resp = client.post("/api/settings/apikey", json={"key": ""})
        assert resp.status_code == 400

    def test_set_active_client(self, client):
        resp = client.post("/api/session/client", json={"code": "abc"})
        assert resp.status_code == 200
        assert resp.json()["active_client_code"] == "abc"

    def test_clear_active_client(self, client):
        resp = client.post("/api/session/client", json={"code": None})
        assert resp.status_code == 200
        assert resp.json()["active_client_code"] is None

    def test_toggle_standard_kb(self, client):
        resp = client.post("/api/session/standard-kb", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["standard_kb_enabled"] is False

        resp = client.post("/api/session/standard-kb", json={"enabled": True})
        assert resp.json()["standard_kb_enabled"] is True


# ───────── Kanban API ─────────


class TestKanbanAPI:
    def _register_and_select(self, client):
        """Helper: register a client and set it as active."""
        client.post("/api/settings/client", json={"code": "KNB", "name": "Kanban Test"})
        client.post("/api/session/client", json={"code": "KNB"})

    def test_list_tickets_no_client(self, client):
        resp = client.get("/api/kanban/tickets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_ticket_no_client(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "Test"})
        assert resp.status_code == 400

    def test_create_ticket(self, client):
        self._register_and_select(client)
        resp = client.post("/api/kanban/tickets", json={
            "title": "Fix IDEX issue",
            "priority": "HIGH",
            "notes": "Check SAP note 12345",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Fix IDEX issue"
        assert data["priority"] == "HIGH"
        assert data["status"] == "NO_ANALIZADO"
        assert data["notes"] == "Check SAP note 12345"

    def test_create_ticket_empty_title(self, client):
        self._register_and_select(client)
        resp = client.post("/api/kanban/tickets", json={"title": ""})
        assert resp.status_code == 400

    def test_list_tickets(self, client):
        self._register_and_select(client)
        client.post("/api/kanban/tickets", json={"title": "T1"})
        client.post("/api/kanban/tickets", json={"title": "T2"})
        resp = client.get("/api/kanban/tickets")
        assert len(resp.json()) == 2

    def test_move_ticket(self, client):
        self._register_and_select(client)
        created = client.post("/api/kanban/tickets", json={"title": "Move me"}).json()
        tid = created["id"]

        resp = client.put(f"/api/kanban/tickets/{tid}/move", json={"status": "ANALIZADO"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ANALIZADO"

    def test_move_ticket_not_found(self, client):
        self._register_and_select(client)
        resp = client.put("/api/kanban/tickets/NONEXIST/move", json={"status": "CERRADO"})
        assert resp.status_code == 404

    def test_move_ticket_empty_status(self, client):
        self._register_and_select(client)
        created = client.post("/api/kanban/tickets", json={"title": "X"}).json()
        resp = client.put(f"/api/kanban/tickets/{created['id']}/move", json={"status": ""})
        assert resp.status_code == 400

    def test_update_ticket(self, client):
        self._register_and_select(client)
        created = client.post("/api/kanban/tickets", json={"title": "Old title"}).json()
        tid = created["id"]

        resp = client.put(f"/api/kanban/tickets/{tid}", json={
            "title": "New title",
            "priority": "CRITICAL",
            "notes": "Updated notes",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "New title"
        assert data["priority"] == "CRITICAL"

    def test_update_ticket_not_found(self, client):
        self._register_and_select(client)
        resp = client.put("/api/kanban/tickets/NONEXIST", json={"title": "X"})
        assert resp.status_code == 404

    def test_ticket_history(self, client):
        self._register_and_select(client)
        created = client.post("/api/kanban/tickets", json={"title": "History test"}).json()
        tid = created["id"]

        client.put(f"/api/kanban/tickets/{tid}/move", json={"status": "ANALIZADO"})
        client.put(f"/api/kanban/tickets/{tid}/move", json={"status": "CERRADO"})

        resp = client.get(f"/api/kanban/tickets/{tid}/history")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) >= 2
        statuses = [h["to_status"] for h in history]
        assert "ANALIZADO" in statuses
        assert "CERRADO" in statuses


# ───────── Kanban Columns API ─────────


class TestKanbanColumnsAPI:
    def _register_and_select(self, client):
        """Helper: register a client and set it as active (needed for ticket operations)."""
        client.post("/api/settings/client", json={"code": "COL", "name": "Column Test"})
        client.post("/api/session/client", json={"code": "COL"})

    def test_list_columns_no_client(self, client):
        """Columns are global - should return defaults even without a client."""
        resp = client.get("/api/kanban/columns")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 8

    def test_list_columns_defaults(self, client):
        resp = client.get("/api/kanban/columns")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 8
        assert data[0]["name"] == "NO_ANALIZADO"
        assert data[1]["name"] == "EN_PROGRESO"
        assert data[2]["name"] == "MAS_INFO"
        assert data[3]["name"] == "TESTING"
        assert data[4]["name"] == "PENDIENTE_DE_TRANSPORTE"
        assert data[5]["name"] == "ANALIZADO_PENDIENTE_RESPUESTA"
        assert data[6]["name"] == "ANALIZADO"
        assert data[7]["name"] == "CERRADO"

    def test_create_column(self, client):
        resp = client.post("/api/kanban/columns", json={
            "name": "CUSTOM",
            "display_name": "Custom",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "CUSTOM"
        assert data["display_name"] == "Custom"
        assert data["position"] == 8

    def test_create_column_without_client_succeeds(self, client):
        """Columns are global - creation works without a client selected."""
        resp = client.post("/api/kanban/columns", json={
            "name": "NOAUTH",
            "display_name": "No auth needed",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "NOAUTH"

    def test_create_column_empty_name(self, client):
        resp = client.post("/api/kanban/columns", json={
            "name": "",
            "display_name": "Test",
        })
        assert resp.status_code == 400

    def test_rename_column(self, client):
        cols = client.get("/api/kanban/columns").json()
        col_id = cols[0]["id"]

        resp = client.put(f"/api/kanban/columns/{col_id}", json={
            "display_name": "Abierto",
        })
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Abierto"

    def test_rename_column_not_found(self, client):
        resp = client.put("/api/kanban/columns/9999", json={
            "display_name": "Ghost",
        })
        assert resp.status_code == 404

    def test_rename_column_empty_name(self, client):
        cols = client.get("/api/kanban/columns").json()
        col_id = cols[0]["id"]
        resp = client.put(f"/api/kanban/columns/{col_id}", json={
            "display_name": "",
        })
        assert resp.status_code == 400

    def test_delete_column(self, client):
        # Create a new column to delete (no tickets)
        created = client.post("/api/kanban/columns", json={
            "name": "TEMP",
            "display_name": "Temp",
        }).json()

        resp = client.delete(f"/api/kanban/columns/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Verify it's gone
        cols = client.get("/api/kanban/columns").json()
        names = [c["name"] for c in cols]
        assert "TEMP" not in names

    def test_delete_column_with_tickets(self, client):
        self._register_and_select(client)
        # Create a ticket in NO_ANALIZADO column (default for new tickets via API)
        client.post("/api/kanban/tickets", json={"title": "Blocker"})

        cols = client.get("/api/kanban/columns").json()
        na_col = next(c for c in cols if c["name"] == "NO_ANALIZADO")

        resp = client.delete(f"/api/kanban/columns/{na_col['id']}")
        assert resp.status_code == 400
        assert "ticket" in resp.json()["error"].lower()

    def test_delete_column_not_found(self, client):
        resp = client.delete("/api/kanban/columns/9999")
        assert resp.status_code == 404

    def test_reorder_columns(self, client):
        cols = client.get("/api/kanban/columns").json()
        # Reverse order
        reversed_ids = [c["id"] for c in reversed(cols)]

        resp = client.put("/api/kanban/columns/reorder", json={
            "ordered_ids": reversed_ids,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["name"] == "CERRADO"
        assert data[-1]["name"] == "NO_ANALIZADO"

    def test_reorder_columns_without_client_succeeds(self, client):
        """Columns are global - reorder works without a client selected."""
        cols = client.get("/api/kanban/columns").json()
        ids = [c["id"] for c in cols]
        resp = client.put("/api/kanban/columns/reorder", json={
            "ordered_ids": ids,
        })
        assert resp.status_code == 200

    def test_reorder_columns_empty(self, client):
        resp = client.put("/api/kanban/columns/reorder", json={
            "ordered_ids": [],
        })
        assert resp.status_code == 400


# ───────── Review API ─────────


class TestReviewAPI:
    def _setup_kb_item(self, client, tmp_path):
        """Helper: create a draft KB item in standard scope."""
        from src.assistant.storage.kb_repository import KBItemRepository
        from src.assistant.storage.models import KBItemType

        db_path = tmp_path / "standard" / "assistant_kb.sqlite"
        repo = KBItemRepository(db_path)
        item, _is_new = repo.create_or_update(
            client_scope="standard",
            client_code=None,
            item_type=KBItemType.RUNBOOK,
            title="Test Runbook",
            content_markdown="# Steps\n1. Do thing",
            tags=["IDEX"],
            sap_objects=["SE38"],
            signals={},
            sources={"test": True},
        )
        return item.kb_id

    def test_list_items_empty(self, client):
        resp = client.get("/api/review/items?scope=standard")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_items_with_data(self, client, tmp_path):
        kb_id = self._setup_kb_item(client, tmp_path)
        resp = client.get("/api/review/items?scope=standard")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["kb_id"] == kb_id
        assert data[0]["status"] == "DRAFT"

    def test_get_item_detail(self, client, tmp_path):
        kb_id = self._setup_kb_item(client, tmp_path)
        resp = client.get(f"/api/review/items/{kb_id}?scope=standard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Runbook"
        assert "IDEX" in data["tags"]

    def test_get_item_not_found(self, client):
        resp = client.get("/api/review/items/nonexistent?scope=standard")
        assert resp.status_code == 404

    @patch("src.web.routers.review.EmbeddingService", create=True)
    @patch("src.web.routers.review.QdrantService", create=True)
    def test_approve_item(self, mock_qdrant_cls, mock_embed_cls, client, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        kb_id = self._setup_kb_item(client, tmp_path)

        mock_embed = MagicMock()
        mock_embed.embed.return_value = [0.1] * 3072
        mock_embed_cls.return_value = mock_embed

        mock_qdrant = MagicMock()
        mock_qdrant_cls.return_value = mock_qdrant

        with patch("src.web.routers.review.EmbeddingService", return_value=mock_embed), \
             patch("src.web.routers.review.QdrantService", return_value=mock_qdrant):
            resp = client.post(f"/api/review/items/{kb_id}/approve", json={
                "scope": "standard",
                "title": "Updated Runbook Title",
                "content_markdown": "# Updated content",
                "tags": ["UPDATED"],
                "sap_objects": ["SE80"],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "APPROVED"
        assert data["title"] == "Updated Runbook Title"

    def test_reject_item(self, client, tmp_path):
        kb_id = self._setup_kb_item(client, tmp_path)
        resp = client.post(f"/api/review/items/{kb_id}/reject", json={"scope": "standard"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"

    def test_list_items_status_filter(self, client, tmp_path):
        self._setup_kb_item(client, tmp_path)

        resp = client.get("/api/review/items?scope=standard&status=DRAFT")
        assert len(resp.json()) == 1

        resp = client.get("/api/review/items?scope=standard&status=APPROVED")
        assert len(resp.json()) == 0


# ───────── Ingest API ─────────


class TestIngestAPI:
    def test_ingest_text_empty(self, client):
        resp = client.post("/api/ingest/text", json={"text": "", "scope": "standard"})
        assert resp.status_code == 400

    def test_ingest_text_no_client_for_client_scope(self, client):
        resp = client.post("/api/ingest/text", json={"text": "Some text", "scope": "client"})
        assert resp.status_code == 400

    @patch("src.web.routers.ingest._run_synthesis")
    def test_ingest_text_returns_202(self, mock_synth, client, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        resp = client.post("/api/ingest/text", json={"text": "SAP IDEX configuration steps", "scope": "standard"})
        assert resp.status_code == 202
        data = resp.json()
        assert "ingestion_id" in data
        assert data["status"] == "queued"

    def test_ingestion_status_not_found(self, client):
        resp = client.get("/api/ingest/nonexistent/status")
        assert resp.status_code == 404

    @patch("src.web.routers.ingest._run_synthesis")
    def test_ingestion_status_after_ingest(self, mock_synth, client, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        resp = client.post("/api/ingest/text", json={"text": "Content here", "scope": "standard"})
        ingestion_id = resp.json()["ingestion_id"]

        status_resp = client.get(f"/api/ingest/{ingestion_id}/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "queued"

    def test_ingest_file_unsupported_type(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("content")

        with open(txt_file, "rb") as f:
            resp = client.post("/api/ingest/file", data={"scope": "standard"}, files={"file": ("test.txt", f, "text/plain")})
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["error"]


# ───────── Chat API ─────────


class TestChatAPI:
    def test_chat_empty_question(self, client):
        resp = client.post("/api/chat/send", json={"question": ""})
        assert resp.status_code == 400

    def test_chat_sends_sse_events(self, client, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        mock_result = MagicMock()
        mock_result.answer = "The IDEX process works as follows..."
        mock_result.sources = []

        with patch("src.web.routers.chat.EmbeddingService", create=True) as mock_embed_cls, \
             patch("src.web.routers.chat.QdrantService", create=True) as mock_qdrant_cls, \
             patch("src.web.routers.chat.ChatService", create=True) as mock_chat_cls, \
             patch("src.web.routers.chat.KBItemRepository", create=True):

            mock_chat = MagicMock()
            mock_chat.answer.return_value = mock_result
            mock_chat_cls.return_value = mock_chat

            resp = client.post("/api/chat/send", json={"question": "How does IDEX work?"})

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


# ───────── Context Pack (preserved from old test_ui.py) ─────────


class TestChatContextPack:
    def test_build_context_pack(self):
        from src.assistant.chat.chat_service import ChatService
        from src.assistant.storage.models import KBItem

        item = KBItem(
            kb_id="test-id",
            client_scope="standard",
            client_code=None,
            type="RUNBOOK",
            title="Test Title",
            content_markdown="# Content here",
            tags_json='["IDEX"]',
            sap_objects_json='["SE38"]',
            signals_json="{}",
            sources_json="{}",
            version=1,
            status="APPROVED",
            content_hash="hash",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )

        pack = ChatService._build_context_pack([(item, 0.95)])
        assert "Test Title" in pack
        assert "RUNBOOK" in pack
        assert "0.950" in pack
        assert "IDEX" in pack
        assert "SE38" in pack


# ───────── Entry point / Module ─────────


class TestWebEntryPoint:
    def test_web_app_importable(self):
        from src.web.app import app, main
        assert app is not None
        assert callable(main)

    def test_main_module_runs_web(self):
        from src.__main__ import main
        assert callable(main)
