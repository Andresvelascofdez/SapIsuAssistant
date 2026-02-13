"""Comprehensive test suite for production readiness."""
import csv
import io
import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.shared.client_manager import ClientManager
from src.assistant.storage.kb_repository import KBItemRepository
from src.assistant.storage.models import KBItemType, KBItemStatus, IngestionStatus
from src.assistant.storage.chat_repository import ChatRepository
from src.assistant.storage.ingestion_repository import IngestionRepository
from src.kanban.storage.kanban_repository import (
    KanbanRepository,
    TicketPriority,
    TicketStatus,
    DEFAULT_COLUMNS,
)
from src.finance.storage.finance_repository import (
    DEFAULT_CATEGORIES,
    FinanceRepository,
    _round2,
)


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════


def _make_api_client(tmp_path, monkeypatch, register_client=None):
    """Create a TestClient with patched DATA_ROOT, optionally registering a client."""
    monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
    import src.web.dependencies as deps
    monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

    from src.web.app import app
    from starlette.testclient import TestClient

    c = TestClient(app)

    if register_client:
        cm = ClientManager(tmp_path)
        cm.register_client(register_client, f"{register_client} Test")
        c.post("/api/session/client", json={"code": register_client})

    return c


def _seed_kb_item(db_path, scope="standard", client_code=None, title="Test Item",
                  content="Test content", item_type=KBItemType.GLOSSARY):
    """Seed a KB item directly via repository."""
    repo = KBItemRepository(db_path)
    item, is_new = repo.create_or_update(
        client_scope=scope,
        client_code=client_code,
        item_type=item_type,
        title=title,
        content_markdown=content,
        tags=["test"],
        sap_objects=["SAP_OBJ"],
        signals={},
        sources={"test": True},
    )
    return item


# ════════════════════════════════════════════════════════════════
# Section 1: Ingest Module Tests
# ════════════════════════════════════════════════════════════════


class TestIngestAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch)

    @pytest.fixture
    def client_with_active(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch, register_client="TST")

    def test_ingest_page_loads(self, client):
        resp = client.get("/ingest")
        assert resp.status_code == 200

    @patch("src.web.routers.ingest._run_synthesis")
    def test_ingest_text_valid(self, mock_synth, client_with_active):
        resp = client_with_active.post("/api/ingest/text", json={
            "text": "SAP IS-U configuration guide for meter reading.",
            "scope": "standard",
        })
        assert resp.status_code == 202
        data = resp.json()
        assert "ingestion_id" in data
        assert data["status"] == "queued"

    def test_ingest_text_empty_rejects(self, client):
        resp = client.post("/api/ingest/text", json={"text": "", "scope": "standard"})
        assert resp.status_code == 400

    def test_ingest_text_whitespace_rejects(self, client):
        resp = client.post("/api/ingest/text", json={"text": "   ", "scope": "standard"})
        assert resp.status_code == 400

    @patch("src.web.routers.ingest._run_synthesis")
    def test_ingest_text_standard_scope(self, mock_synth, client_with_active):
        resp = client_with_active.post("/api/ingest/text", json={
            "text": "Standard KB content",
            "scope": "standard",
        })
        assert resp.status_code == 202

    def test_ingest_text_client_scope_requires_client(self, client):
        resp = client.post("/api/ingest/text", json={
            "text": "Client-specific content",
            "scope": "client",
        })
        assert resp.status_code == 400
        assert "client" in resp.json()["error"].lower()

    @patch("src.web.routers.ingest._run_synthesis")
    def test_ingest_text_client_scope_with_client(self, mock_synth, client_with_active):
        resp = client_with_active.post("/api/ingest/text", json={
            "text": "Client-specific content for TST",
            "scope": "client",
        })
        assert resp.status_code == 202

    @patch("src.web.routers.ingest._run_synthesis")
    @patch("src.assistant.ingestion.extractors.extract_pdf")
    def test_ingest_file_pdf(self, mock_extract, mock_synth, client_with_active):
        from src.assistant.ingestion.extractors import ExtractionResult
        mock_extract.return_value = ExtractionResult(
            text="Extracted PDF text", input_hash="abc123", input_kind="pdf", input_name="test.pdf",
        )
        resp = client_with_active.post(
            "/api/ingest/file",
            files={"file": ("test.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")},
            data={"scope": "standard"},
        )
        assert resp.status_code == 202
        assert "ingestion_id" in resp.json()

    @patch("src.web.routers.ingest._run_synthesis")
    def test_ingest_file_docx(self, mock_synth, client_with_active, tmp_path):
        # Create a minimal docx-like file (real docx needs python-docx)
        from docx import Document
        doc = Document()
        doc.add_paragraph("Test DOCX content")
        docx_path = tmp_path / "test.docx"
        doc.save(str(docx_path))
        content = docx_path.read_bytes()

        resp = client_with_active.post(
            "/api/ingest/file",
            files={"file": ("test.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"scope": "standard"},
        )
        assert resp.status_code == 202

    def test_ingest_file_unsupported_type(self, client_with_active):
        resp = client_with_active.post(
            "/api/ingest/file",
            files={"file": ("test.exe", b"MZ executable", "application/octet-stream")},
            data={"scope": "standard"},
        )
        assert resp.status_code == 400

    def test_ingest_status_nonexistent_id(self, client):
        resp = client.get("/api/ingest/nonexistent-id/status")
        assert resp.status_code == 404

    @patch("src.web.routers.ingest._run_synthesis")
    def test_ingest_status_valid_id(self, mock_synth, client_with_active):
        resp = client_with_active.post("/api/ingest/text", json={
            "text": "Content for status check",
            "scope": "standard",
        })
        ingestion_id = resp.json()["ingestion_id"]
        resp = client_with_active.get(f"/api/ingest/{ingestion_id}/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    def test_ingest_file_client_scope_requires_client(self, client):
        resp = client.post(
            "/api/ingest/file",
            files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")},
            data={"scope": "client"},
        )
        assert resp.status_code == 400


# ════════════════════════════════════════════════════════════════
# Section 2: Review Module Tests
# ════════════════════════════════════════════════════════════════


class TestReviewAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        c = _make_api_client(tmp_path, monkeypatch, register_client="TST")
        # Seed standard KB items
        cm = ClientManager(tmp_path)
        std_db = cm.get_standard_dir() / "assistant_kb.sqlite"
        _seed_kb_item(std_db, scope="standard", title="Standard Glossary")
        _seed_kb_item(std_db, scope="standard", title="Another Item",
                      item_type=KBItemType.RESOLUTION)
        # Seed client KB item
        client_db = cm.get_client_dir("TST") / "assistant_kb.sqlite"
        _seed_kb_item(client_db, scope="client", client_code="TST", title="Client Item")
        return c

    def test_review_page_loads(self, client):
        resp = client.get("/review")
        assert resp.status_code == 200

    def test_list_items_standard_scope(self, client):
        resp = client.get("/api/review/items?scope=standard")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        titles = [i["title"] for i in data]
        assert "Standard Glossary" in titles

    def test_list_items_client_scope(self, client):
        resp = client.get("/api/review/items?scope=client")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Client Item"

    def test_list_items_filter_by_status_draft(self, client):
        resp = client.get("/api/review/items?scope=standard&status=DRAFT")
        assert resp.status_code == 200
        data = resp.json()
        assert all(i["status"] == "DRAFT" for i in data)

    def test_list_items_empty_scope(self, tmp_path, monkeypatch):
        c = _make_api_client(tmp_path, monkeypatch)
        resp = c.get("/api/review/items?scope=standard")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    def test_get_item_exists(self, client):
        items_resp = client.get("/api/review/items?scope=standard")
        kb_id = items_resp.json()[0]["kb_id"]
        resp = client.get(f"/api/review/items/{kb_id}?scope=standard")
        assert resp.status_code == 200
        assert resp.json()["kb_id"] == kb_id

    def test_get_item_not_found(self, client):
        resp = client.get("/api/review/items/nonexistent?scope=standard")
        assert resp.status_code == 404

    def test_approve_item(self, client):
        items_resp = client.get("/api/review/items?scope=standard")
        kb_id = items_resp.json()[0]["kb_id"]
        resp = client.post(f"/api/review/items/{kb_id}/approve", json={"scope": "standard"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "APPROVED"

    def test_approve_item_with_edits(self, client):
        items_resp = client.get("/api/review/items?scope=standard")
        kb_id = items_resp.json()[0]["kb_id"]
        resp = client.post(f"/api/review/items/{kb_id}/approve", json={
            "scope": "standard",
            "title": "Edited Title",
            "content_markdown": "Edited content",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Edited Title"
        assert data["content_markdown"] == "Edited content"
        assert data["status"] == "APPROVED"

    def test_reject_item(self, client):
        items_resp = client.get("/api/review/items?scope=standard")
        kb_id = items_resp.json()[0]["kb_id"]
        resp = client.post(f"/api/review/items/{kb_id}/reject", json={"scope": "standard"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"

    def test_approve_then_list_shows_approved(self, client):
        items_resp = client.get("/api/review/items?scope=standard")
        kb_id = items_resp.json()[0]["kb_id"]
        client.post(f"/api/review/items/{kb_id}/approve", json={"scope": "standard"})
        resp = client.get("/api/review/items?scope=standard&status=APPROVED")
        assert resp.status_code == 200
        data = resp.json()
        approved_ids = [i["kb_id"] for i in data]
        assert kb_id in approved_ids

    def test_list_items_client_no_active_client(self, tmp_path, monkeypatch):
        c = _make_api_client(tmp_path, monkeypatch)
        resp = c.get("/api/review/items?scope=client")
        assert resp.status_code == 200
        assert resp.json() == []


# ════════════════════════════════════════════════════════════════
# Section 3: Settings Module Tests
# ════════════════════════════════════════════════════════════════


class TestSettingsAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch)

    def test_settings_page_loads(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200

    def test_register_client(self, client):
        resp = client.post("/api/settings/client", json={"code": "ABC", "name": "ABC Corp"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "ABC"
        assert data["name"] == "ABC Corp"

    def test_register_client_empty_code_rejects(self, client):
        resp = client.post("/api/settings/client", json={"code": "", "name": "Test"})
        assert resp.status_code == 400

    def test_register_client_empty_name_rejects(self, client):
        resp = client.post("/api/settings/client", json={"code": "XYZ", "name": ""})
        assert resp.status_code == 400

    def test_register_duplicate_client_rejects(self, client):
        client.post("/api/settings/client", json={"code": "DUP", "name": "First"})
        resp = client.post("/api/settings/client", json={"code": "DUP", "name": "Second"})
        assert resp.status_code == 400

    def test_list_clients_empty(self, client):
        resp = client.get("/api/settings/clients")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_clients_after_register(self, client):
        client.post("/api/settings/client", json={"code": "CL1", "name": "Client 1"})
        client.post("/api/settings/client", json={"code": "CL2", "name": "Client 2"})
        resp = client.get("/api/settings/clients")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        codes = [c["code"] for c in data]
        assert "CL1" in codes
        assert "CL2" in codes

    def test_set_qdrant_url(self, client):
        resp = client.post("/api/settings/qdrant", json={"url": "http://my-qdrant:6333"})
        assert resp.status_code == 200
        assert resp.json()["qdrant_url"] == "http://my-qdrant:6333"

    def test_set_qdrant_url_empty_rejects(self, client):
        resp = client.post("/api/settings/qdrant", json={"url": ""})
        assert resp.status_code == 400

    def test_set_apikey(self, client):
        resp = client.post("/api/settings/apikey", json={"key": "sk-test123"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_set_apikey_empty_rejects(self, client):
        resp = client.post("/api/settings/apikey", json={"key": ""})
        assert resp.status_code == 400

    def test_set_active_client(self, client):
        client.post("/api/settings/client", json={"code": "ACT", "name": "Active"})
        resp = client.post("/api/session/client", json={"code": "ACT"})
        assert resp.status_code == 200
        assert resp.json()["active_client_code"] == "ACT"

    def test_set_active_client_none_clears(self, client):
        resp = client.post("/api/session/client", json={"code": None})
        assert resp.status_code == 200
        assert resp.json()["active_client_code"] is None

    def test_toggle_standard_kb(self, client):
        resp = client.post("/api/session/standard-kb", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["standard_kb_enabled"] is False
        resp = client.post("/api/session/standard-kb", json={"enabled": True})
        assert resp.json()["standard_kb_enabled"] is True

    def test_set_stale_days_valid(self, client):
        resp = client.post("/api/settings/stale-days", json={"days": 5})
        assert resp.status_code == 200
        assert resp.json()["days"] == 5

    def test_set_stale_days_zero_rejects(self, client):
        resp = client.post("/api/settings/stale-days", json={"days": 0})
        assert resp.status_code == 400

    def test_set_stale_days_negative_rejects(self, client):
        resp = client.post("/api/settings/stale-days", json={"days": -1})
        assert resp.status_code == 400

    def test_set_stale_days_float_rejects(self, client):
        resp = client.post("/api/settings/stale-days", json={"days": 3.5})
        assert resp.status_code == 400


# ════════════════════════════════════════════════════════════════
# Section 4: Client Manager Unit Tests
# ════════════════════════════════════════════════════════════════


class TestClientManager:
    def test_register_creates_directory(self, tmp_path):
        cm = ClientManager(tmp_path)
        cm.register_client("ABC", "ABC Corp")
        assert (tmp_path / "clients" / "ABC").is_dir()

    def test_register_creates_subdirs(self, tmp_path):
        cm = ClientManager(tmp_path)
        cm.register_client("ABC", "ABC Corp")
        client_dir = tmp_path / "clients" / "ABC"
        assert (client_dir / "uploads").is_dir()

    def test_register_creates_kanban_sqlite(self, tmp_path):
        cm = ClientManager(tmp_path)
        cm.register_client("ABC", "ABC Corp")
        assert (tmp_path / "clients" / "ABC" / "kanban.sqlite").exists()

    def test_register_creates_kb_sqlite(self, tmp_path):
        cm = ClientManager(tmp_path)
        cm.register_client("ABC", "ABC Corp")
        assert (tmp_path / "clients" / "ABC" / "assistant_kb.sqlite").exists()

    def test_get_client_exists(self, tmp_path):
        cm = ClientManager(tmp_path)
        cm.register_client("XYZ", "XYZ Corp")
        client = cm.get_client("XYZ")
        assert client is not None
        assert client.code == "XYZ"
        assert client.name == "XYZ Corp"

    def test_get_client_not_found(self, tmp_path):
        cm = ClientManager(tmp_path)
        assert cm.get_client("NOPE") is None

    def test_list_clients_ordered(self, tmp_path):
        cm = ClientManager(tmp_path)
        cm.register_client("ZZZ", "Last")
        cm.register_client("AAA", "First")
        cm.register_client("MMM", "Middle")
        clients = cm.list_clients()
        codes = [c.code for c in clients]
        assert codes == ["AAA", "MMM", "ZZZ"]

    def test_client_code_uppercased(self, tmp_path):
        cm = ClientManager(tmp_path)
        client = cm.register_client("abc", "Lower Case")
        assert client.code == "ABC"
        assert cm.get_client("abc").code == "ABC"

    def test_get_client_dir(self, tmp_path):
        cm = ClientManager(tmp_path)
        path = cm.get_client_dir("TST")
        assert path == tmp_path / "clients" / "TST"

    def test_get_standard_dir(self, tmp_path):
        cm = ClientManager(tmp_path)
        path = cm.get_standard_dir()
        assert path == tmp_path / "standard"
        assert path.is_dir()
        assert (path / "uploads").is_dir()
        assert (path / "assistant_kb.sqlite").exists()

    def test_register_duplicate_raises(self, tmp_path):
        cm = ClientManager(tmp_path)
        cm.register_client("DUP", "First")
        with pytest.raises(ValueError, match="already exists"):
            cm.register_client("DUP", "Second")

    def test_register_empty_code_raises(self, tmp_path):
        cm = ClientManager(tmp_path)
        with pytest.raises(ValueError, match="empty"):
            cm.register_client("", "Name")

    def test_register_empty_name_raises(self, tmp_path):
        cm = ClientManager(tmp_path)
        with pytest.raises(ValueError, match="empty"):
            cm.register_client("CODE", "")


# ════════════════════════════════════════════════════════════════
# Section 5: KB Repository Edge Cases
# ════════════════════════════════════════════════════════════════


class TestKBRepositoryEdgeCases:
    def test_create_item_draft_status(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        item, is_new = repo.create_or_update(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY, title="Test",
            content_markdown="Content", tags=[], sap_objects=[], signals={}, sources={},
        )
        assert item.status == "DRAFT"
        assert is_new is True

    def test_dedup_same_content_returns_existing(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        kwargs = dict(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY, title="Same Title",
            content_markdown="Same Content", tags=[], sap_objects=[], signals={}, sources={},
        )
        item1, new1 = repo.create_or_update(**kwargs)
        item2, new2 = repo.create_or_update(**kwargs)
        assert item1.kb_id == item2.kb_id
        assert new1 is True
        assert new2 is False

    def test_version_increment_different_content(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        base = dict(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY, title="Versioned",
            tags=[], sap_objects=[], signals={}, sources={},
        )
        item1, _ = repo.create_or_update(content_markdown="Version 1", **base)
        item2, new2 = repo.create_or_update(content_markdown="Version 2", **base)
        assert item1.kb_id == item2.kb_id
        assert item2.version == 2
        assert new2 is False

    def test_new_item_different_title(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        base = dict(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY,
            content_markdown="Content", tags=[], sap_objects=[], signals={}, sources={},
        )
        item1, _ = repo.create_or_update(title="Title A", **base)
        item2, new2 = repo.create_or_update(title="Title B", **base)
        assert item1.kb_id != item2.kb_id
        assert new2 is True

    def test_list_by_scope_standard(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        repo.create_or_update(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY, title="Std",
            content_markdown="C", tags=[], sap_objects=[], signals={}, sources={},
        )
        repo.create_or_update(
            client_scope="client", client_code="TST",
            item_type=KBItemType.GLOSSARY, title="Client",
            content_markdown="C", tags=[], sap_objects=[], signals={}, sources={},
        )
        std_items = repo.list_by_scope("standard")
        assert len(std_items) == 1
        assert std_items[0].title == "Std"

    def test_list_by_scope_client(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        repo.create_or_update(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY, title="Std",
            content_markdown="C", tags=[], sap_objects=[], signals={}, sources={},
        )
        repo.create_or_update(
            client_scope="client", client_code="TST",
            item_type=KBItemType.GLOSSARY, title="Client",
            content_markdown="C", tags=[], sap_objects=[], signals={}, sources={},
        )
        client_items = repo.list_by_scope("client", client_code="TST")
        assert len(client_items) == 1
        assert client_items[0].title == "Client"

    def test_update_status_approved(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        item, _ = repo.create_or_update(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY, title="To Approve",
            content_markdown="C", tags=[], sap_objects=[], signals={}, sources={},
        )
        updated = repo.update_status(item.kb_id, KBItemStatus.APPROVED)
        assert updated.status == "APPROVED"

    def test_update_status_rejected(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        item, _ = repo.create_or_update(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY, title="To Reject",
            content_markdown="C", tags=[], sap_objects=[], signals={}, sources={},
        )
        updated = repo.update_status(item.kb_id, KBItemStatus.REJECTED)
        assert updated.status == "REJECTED"

    def test_update_status_nonexistent(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        result = repo.update_status("nonexistent", KBItemStatus.APPROVED)
        assert result is None

    def test_update_fields_recomputes_hash(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        item, _ = repo.create_or_update(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY, title="Original",
            content_markdown="Original content", tags=[], sap_objects=[], signals={}, sources={},
        )
        original_hash = item.content_hash
        updated = repo.update_fields(item.kb_id, content_markdown="Changed content")
        assert updated.content_hash != original_hash

    def test_create_with_tags_and_sap_objects(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        item, _ = repo.create_or_update(
            client_scope="standard", client_code=None,
            item_type=KBItemType.GLOSSARY, title="Tagged",
            content_markdown="C",
            tags=["tag1", "tag2"],
            sap_objects=["ZCL_TEST", "BAPI_METER"],
            signals={"confidence": 0.9}, sources={},
        )
        assert json.loads(item.tags_json) == ["tag1", "tag2"]
        assert json.loads(item.sap_objects_json) == ["ZCL_TEST", "BAPI_METER"]
        assert json.loads(item.signals_json)["confidence"] == 0.9

    def test_get_nonexistent_item(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        assert repo.get_by_id("nonexistent") is None

    def test_update_fields_nonexistent(self, tmp_path):
        repo = KBItemRepository(tmp_path / "kb.db")
        result = repo.update_fields("nonexistent", title="New")
        assert result is None


# ════════════════════════════════════════════════════════════════
# Section 6: Chat Repository Edge Cases
# ════════════════════════════════════════════════════════════════


class TestChatRepositoryEdgeCases:
    def test_create_session_default_title(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        session = repo.create_session(scope="general")
        assert session.title == "New Chat"

    def test_create_session_custom_title(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        session = repo.create_session(scope="general", title="My Topic")
        assert session.title == "My Topic"

    def test_add_message_updates_last_message_at(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        session = repo.create_session(scope="general")
        original_last = session.last_message_at
        time.sleep(0.01)
        repo.add_message(session.session_id, role="user", content="Hello")
        updated = repo.get_session(session.session_id)
        assert updated.last_message_at >= original_last

    def test_list_sessions_pinned_first(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s1 = repo.create_session(scope="general", title="Unpinned")
        s2 = repo.create_session(scope="general", title="Pinned")
        repo.pin_session(s2.session_id, True)
        sessions = repo.list_sessions()
        assert sessions[0].title == "Pinned"
        assert sessions[0].is_pinned == 1

    def test_list_sessions_pagination(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        for i in range(5):
            repo.create_session(scope="general", title=f"Session {i}")
        page1 = repo.list_sessions(limit=2, offset=0)
        page2 = repo.list_sessions(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0].session_id != page2[0].session_id

    def test_search_sessions_by_title(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        repo.create_session(scope="general", title="Meter Reading Guide")
        repo.create_session(scope="general", title="Billing FAQ")
        results = repo.search_sessions("Meter")
        assert len(results) == 1
        assert results[0].title == "Meter Reading Guide"

    def test_search_sessions_by_message_content(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general", title="Generic Session")
        repo.add_message(s.session_id, role="user", content="How to configure ABAP transaction?")
        results = repo.search_sessions("ABAP")
        assert len(results) == 1

    def test_search_no_results(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        repo.create_session(scope="general", title="Something")
        results = repo.search_sessions("nonexistent_query_xyz")
        assert len(results) == 0

    def test_delete_session_cascades_messages(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general")
        repo.add_message(s.session_id, role="user", content="Hello")
        repo.add_message(s.session_id, role="assistant", content="Hi there")
        assert len(repo.get_messages(s.session_id)) == 2
        repo.delete_session(s.session_id)
        assert repo.get_session(s.session_id) is None
        assert len(repo.get_messages(s.session_id)) == 0

    def test_export_empty_session_markdown(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general", title="Empty")
        md = repo.export_session_markdown(s.session_id)
        assert md is not None
        assert "# Empty" in md

    def test_export_empty_session_json(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general", title="Empty")
        j = repo.export_session_json(s.session_id)
        assert j is not None
        data = json.loads(j)
        assert data["title"] == "Empty"
        assert data["messages"] == []

    def test_retention_deletes_old_unpinned(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general", title="Old")
        # Manually backdate last_message_at
        old_date = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        with sqlite3.connect(tmp_path / "chat.db") as conn:
            conn.execute(
                "UPDATE chat_sessions SET last_message_at = ? WHERE session_id = ?",
                (old_date, s.session_id),
            )
            conn.commit()
        deleted = repo.cleanup_retention(retention_days=5)
        assert deleted == 1
        assert repo.get_session(s.session_id) is None

    def test_retention_preserves_pinned(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general", title="Pinned Old")
        repo.pin_session(s.session_id, True)
        old_date = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        with sqlite3.connect(tmp_path / "chat.db") as conn:
            conn.execute(
                "UPDATE chat_sessions SET last_message_at = ? WHERE session_id = ?",
                (old_date, s.session_id),
            )
            conn.commit()
        deleted = repo.cleanup_retention(retention_days=1)
        assert deleted == 0
        assert repo.get_session(s.session_id) is not None

    def test_add_message_role_user(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general")
        msg = repo.add_message(s.session_id, role="user", content="Question?")
        assert msg.role == "user"

    def test_add_message_role_assistant(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general")
        msg = repo.add_message(s.session_id, role="assistant", content="Answer.")
        assert msg.role == "assistant"

    def test_add_message_with_kb_items_json(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general")
        kb_json = json.dumps(["kb-1", "kb-2"])
        msg = repo.add_message(s.session_id, role="assistant", content="R",
                               used_kb_items_json=kb_json, model_called=1)
        exported = repo.export_session_json(s.session_id)
        data = json.loads(exported)
        assert data["messages"][0]["used_kb_items"] == ["kb-1", "kb-2"]
        assert data["messages"][0]["model_called"] is True

    def test_export_nonexistent_session(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        assert repo.export_session_markdown("nonexistent") is None
        assert repo.export_session_json("nonexistent") is None

    def test_rename_session(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general", title="Old Name")
        renamed = repo.rename_session(s.session_id, "New Name")
        assert renamed.title == "New Name"


# ════════════════════════════════════════════════════════════════
# Section 7: Kanban Repository Edge Cases
# ════════════════════════════════════════════════════════════════


class TestKanbanRepositoryEdgeCases:
    def test_create_ticket_default_priority(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Default Priority")
        assert t.priority == "MEDIUM"

    def test_create_ticket_with_description(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Has Desc", description="Detailed description")
        assert t.description == "Detailed description"

    def test_update_status_records_history(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Track History")
        repo.update_status(t.id, "TESTING")
        history = repo.get_history(t.id)
        assert len(history) == 2  # creation + update
        assert history[0].from_status is None
        assert history[0].to_status == "EN_PROGRESO"
        assert history[1].from_status == "EN_PROGRESO"
        assert history[1].to_status == "TESTING"

    def test_update_status_cerrado_sets_closed_at(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="To Close")
        updated = repo.update_status(t.id, "CERRADO")
        assert updated.closed_at is not None

    def test_update_status_done_sets_closed_at(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Done")
        updated = repo.update_status(t.id, "DONE")
        assert updated.closed_at is not None

    def test_update_status_reopen_keeps_closed_at(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Reopen")
        repo.update_status(t.id, "CERRADO")
        reopened = repo.update_status(t.id, "EN_PROGRESO")
        # COALESCE keeps the original closed_at
        assert reopened.closed_at is not None

    def test_search_description(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="T1", description="The meter reading issue")
        repo.create_ticket(title="T2", description="Billing problem")
        results = repo.list_tickets(search="meter")
        assert len(results) == 1
        assert results[0].title == "T1"

    def test_search_no_match(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="Alpha")
        results = repo.list_tickets(search="zzz_nonexistent")
        assert len(results) == 0

    def test_list_tickets_no_filters(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="A")
        repo.create_ticket(title="B")
        repo.create_ticket(title="C")
        assert len(repo.list_tickets()) == 3

    def test_list_tickets_status_filter(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="Progress", status="EN_PROGRESO")
        repo.create_ticket(title="Testing", status="TESTING")
        results = repo.list_tickets(status="TESTING")
        assert len(results) == 1
        assert results[0].title == "Testing"

    def test_count_tickets_matches_list(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        for i in range(5):
            repo.create_ticket(title=f"T{i}")
        assert repo.count_tickets() == len(repo.list_tickets())
        assert repo.count_tickets(status="EN_PROGRESO") == len(repo.list_tickets(status="EN_PROGRESO"))

    def test_delete_cascade_history(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Del")
        repo.update_status(t.id, "TESTING")
        assert len(repo.get_history(t.id)) >= 2
        repo.delete_ticket(t.id)
        assert len(repo.get_history(t.id)) == 0

    def test_ticket_id_exists_across_tickets(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="A", ticket_id="SWE-001")
        repo.create_ticket(title="B", ticket_id="SWE-002")
        assert repo.ticket_id_exists("SWE-001") is True
        assert repo.ticket_id_exists("SWE-003") is False

    def test_ticket_id_exists_exclude_self(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="A", ticket_id="SWE-001")
        assert repo.ticket_id_exists("SWE-001", exclude_id=t.id) is False
        repo.create_ticket(title="B", ticket_id="SWE-001")  # another with same ticket_id
        assert repo.ticket_id_exists("SWE-001", exclude_id=t.id) is True

    def test_empty_tags_and_links(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Empty Meta", tags=[], links=[])
        assert json.loads(t.tags_json) == []
        assert json.loads(t.links_json) == []

    def test_stale_ids_empty_when_recent(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="Fresh")
        stale = repo.get_stale_ticket_ids(days=1)
        assert len(stale) == 0

    def test_column_management(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        columns = repo.list_columns()
        assert len(columns) == len(DEFAULT_COLUMNS)
        new_col = repo.create_column("CUSTOM", "Custom Column")
        assert new_col.name == "CUSTOM"
        renamed = repo.rename_column(new_col.id, "Renamed Custom")
        assert renamed.display_name == "Renamed Custom"
        assert repo.delete_column(new_col.id) is True

    def test_delete_column_with_tickets_raises(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="Blocker", status="EN_PROGRESO")
        cols = repo.list_columns()
        en_progreso_col = next(c for c in cols if c.name == "EN_PROGRESO")
        with pytest.raises(ValueError, match="ticket"):
            repo.delete_column(en_progreso_col.id)

    def test_update_ticket_fields(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Original", priority="LOW")
        updated = repo.update_ticket(t.id, title="Updated", priority="HIGH")
        assert updated.title == "Updated"
        assert updated.priority == "HIGH"

    def test_update_ticket_no_fields(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        t = repo.create_ticket(title="Unchanged")
        result = repo.update_ticket(t.id)
        assert result.title == "Unchanged"


# ════════════════════════════════════════════════════════════════
# Section 8: Kanban API Edge Cases
# ════════════════════════════════════════════════════════════════


class TestKanbanAPIEdgeCases:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch, register_client="TST")

    @pytest.fixture
    def client_no_active(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch)

    def test_create_ticket_empty_title_rejects(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": ""})
        assert resp.status_code == 400

    def test_create_ticket_whitespace_title_rejects(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "   "})
        assert resp.status_code == 400

    def test_create_ticket_success(self, client):
        resp = client.post("/api/kanban/tickets", json={
            "title": "New Task",
            "priority": "HIGH",
            "description": "Task description",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "New Task"
        assert data["priority"] == "HIGH"

    def test_move_ticket(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "To Move"})
        tid = resp.json()["id"]
        resp = client.put(f"/api/kanban/tickets/{tid}/move", json={"status": "TESTING"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "TESTING"

    def test_move_ticket_empty_status_rejects(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "T"})
        tid = resp.json()["id"]
        resp = client.put(f"/api/kanban/tickets/{tid}/move", json={"status": ""})
        assert resp.status_code == 400

    def test_update_ticket_no_fields(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "Unchanged"})
        tid = resp.json()["id"]
        resp = client.put(f"/api/kanban/tickets/{tid}", json={})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Unchanged"

    def test_columns_api_create(self, client):
        resp = client.post("/api/kanban/columns", json={
            "name": "NEW_COL",
            "display_name": "New Column",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "NEW_COL"

    def test_columns_api_rename(self, client):
        cols_resp = client.get("/api/kanban/columns")
        col = cols_resp.json()[0]
        resp = client.put(f"/api/kanban/columns/{col['id']}", json={
            "display_name": "Renamed",
        })
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Renamed"

    def test_columns_api_delete_empty(self, client):
        resp = client.post("/api/kanban/columns", json={
            "name": "TO_DELETE",
            "display_name": "To Delete",
        })
        col_id = resp.json()["id"]
        resp = client.delete(f"/api/kanban/columns/{col_id}")
        assert resp.status_code == 200

    def test_columns_api_delete_with_tickets_rejects(self, client):
        # Create a ticket in EN_PROGRESO
        client.post("/api/kanban/tickets", json={"title": "Blocker"})
        # Try to delete EN_PROGRESO column
        cols_resp = client.get("/api/kanban/columns")
        en_progreso = next(c for c in cols_resp.json() if c["name"] == "EN_PROGRESO")
        # First figure out what default status is used
        # The ticket was put in the first column's status
        cols = cols_resp.json()
        first_col = cols[0]
        resp = client.delete(f"/api/kanban/columns/{first_col['id']}")
        assert resp.status_code == 400

    def test_export_csv_empty(self, client):
        resp = client.get("/api/kanban/export-csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        content = resp.content.decode("utf-8-sig")
        lines = content.strip().split("\n")
        assert len(lines) == 1  # header only

    def test_export_csv_with_data(self, client):
        client.post("/api/kanban/tickets", json={"title": "CSV Task", "priority": "HIGH"})
        resp = client.get("/api/kanban/export-csv")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8-sig")
        assert "CSV Task" in content
        assert "HIGH" in content

    def test_list_tickets_all_clients_no_session(self, client_no_active, tmp_path):
        # Register two clients and create tickets for each
        cm = ClientManager(tmp_path)
        cm.register_client("AAA", "Client A")
        cm.register_client("BBB", "Client B")
        repo_a = KanbanRepository(tmp_path / "clients" / "AAA" / "kanban.sqlite", seed_columns=False)
        repo_b = KanbanRepository(tmp_path / "clients" / "BBB" / "kanban.sqlite", seed_columns=False)
        repo_a.create_ticket(title="A Ticket")
        repo_b.create_ticket(title="B Ticket")
        resp = client_no_active.get("/api/kanban/tickets")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_stale_info_default_days(self, client):
        resp = client.get("/api/kanban/stale-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "stale_count" in data
        assert "stale_ids" in data

    def test_history_for_new_ticket(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "Fresh"})
        tid = resp.json()["id"]
        resp = client.get(f"/api/kanban/tickets/{tid}/history")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) == 1  # creation entry
        assert history[0]["from_status"] is None

    def test_delete_ticket_api(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "To Delete"})
        tid = resp.json()["id"]
        resp = client.delete(f"/api/kanban/tickets/{tid}")
        assert resp.status_code == 200

    def test_delete_nonexistent_ticket_api(self, client):
        resp = client.delete("/api/kanban/tickets/nonexistent")
        assert resp.status_code == 404

    def test_import_csv_nonexistent_path(self, client):
        resp = client.post("/api/kanban/import-csv", json={"csv_path": "/nonexistent/file.csv"})
        assert resp.status_code == 400

    def test_import_csv_empty_path_rejects(self, client):
        resp = client.post("/api/kanban/import-csv", json={"csv_path": ""})
        assert resp.status_code == 400

    def test_import_csv_valid(self, client, tmp_path):
        csv_content = "Cliente,ID Tarea,Nombre de tarea,Estado,Prioridad,Tipo de tarea,Texto,Horas,Responsable\n"
        csv_content += "TST,TST-001,Test Task,En progreso,Alta,Bug,Descripcion,2,John\n"
        csv_file = tmp_path / "import.csv"
        csv_file.write_text(csv_content, encoding="utf-8-sig")
        resp = client.post("/api/kanban/import-csv", json={"csv_path": str(csv_file)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["per_client"]["TST"] == 1


# ════════════════════════════════════════════════════════════════
# Section 9: Finance Module Edge Cases
# ════════════════════════════════════════════════════════════════


class TestFinanceEdgeCases:
    def test_create_expense_zero_amount(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        e = repo.create_expense(period_year=2025, period_month=1,
                                category_id=cats[0].id, amount=0.0)
        assert e.amount == 0.0

    def test_create_expense_negative_amount(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        e = repo.create_expense(period_year=2025, period_month=1,
                                category_id=cats[0].id, amount=-10.0)
        assert e.amount == -10.0

    def test_update_expense_no_fields(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        e = repo.create_expense(period_year=2025, period_month=1,
                                category_id=cats[0].id, amount=50.0)
        result = repo.update_expense(e.id)
        assert result.amount == 50.0

    def test_invoice_number_duplicate(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv1 = repo.create_invoice(period_year=2025, period_month=1,
                                   client_name="A", invoice_number="INV-001")
        inv2 = repo.create_invoice(period_year=2025, period_month=1,
                                   client_name="B", invoice_number="INV-001")
        assert inv1.id != inv2.id
        assert inv1.invoice_number == inv2.invoice_number

    def test_invoice_status_values(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(period_year=2025, period_month=1,
                                  client_name="A", invoice_number="INV-S")
        assert inv.status == "PENDING"
        updated = repo.update_invoice(inv.id, status="PAID")
        assert updated.status == "PAID"

    def test_invoice_with_0_quantity_item(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=1,
            client_name="A", invoice_number="INV-Z",
            items=[{"description": "Free", "quantity": 0, "unit_price": 100.0, "unit": "HOURS"}],
        )
        assert inv.subtotal == 0.0
        assert inv.total == 0.0

    def test_vat_rate_100_percent(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=1,
            client_name="A", invoice_number="INV-VAT100",
            vat_rate=1.0,
            items=[{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        )
        assert inv.subtotal == 1000.0
        assert inv.vat_amount == 1000.0
        assert inv.total == 2000.0

    def test_category_name_duplicate_rejects(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        repo.create_category("Unique")
        with pytest.raises(Exception):
            repo.create_category("Unique")

    def test_document_sha256_without_file_bytes(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        doc = repo.create_document(
            original_file_name="test.txt",
            mime_type="text/plain",
            size_bytes=100,
            storage_path="test/path.txt",
            file_bytes=None,
        )
        assert doc.sha256 is None

    def test_document_sha256_with_file_bytes(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        doc = repo.create_document(
            original_file_name="test.txt",
            mime_type="text/plain",
            size_bytes=5,
            storage_path="test/path.txt",
            file_bytes=b"hello",
        )
        assert doc.sha256 is not None
        assert len(doc.sha256) == 64

    def test_summary_all_months_empty(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        months = repo.get_yearly_summary(2025)
        for m in months:
            assert m["incomes"] == 0.0
            assert m["expenses"] == 0.0
            assert m["profit"] == 0.0

    def test_summary_with_only_expenses(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        repo.create_expense(period_year=2025, period_month=1,
                            category_id=cats[0].id, amount=500.0)
        s = repo.get_monthly_summary(2025, 1)
        assert s["profit"] == -500.0
        assert s["tax"] == 0.0
        assert s["net"] == 0.0  # net = incomes - tax; expenses are personal, not deducted from net
        assert s["net_business"] == -500.0  # net_business = 0 - 500 - 0 = -500

    def test_ocr_extract_multiple_dates(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("First: 2025-01-15, Second: 2025-06-20")
        assert len(dates) >= 2
        assert (2025, 1) in dates

    def test_ocr_extract_multiple_amounts(self):
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("SUBTOTAL: 100.00\nTOTAL: 250.00")
        assert 100.0 in amounts
        assert 250.0 in amounts

    def test_ocr_european_comma_decimal(self):
        from src.finance.ocr.ocr_service import _parse_number
        assert _parse_number("1.234,56") == 1234.56


# ════════════════════════════════════════════════════════════════
# Section 10: End-to-End Workflow Tests
# ════════════════════════════════════════════════════════════════


class TestE2EClientSetup:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch)

    def test_register_and_activate_client(self, client):
        # Register
        resp = client.post("/api/settings/client", json={"code": "E2E", "name": "E2E Client"})
        assert resp.status_code == 200
        assert resp.json()["code"] == "E2E"
        # Activate
        resp = client.post("/api/session/client", json={"code": "E2E"})
        assert resp.json()["active_client_code"] == "E2E"
        # Create ticket
        resp = client.post("/api/kanban/tickets", json={"title": "E2E Ticket"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "E2E Ticket"

    def test_two_clients_ticket_isolation(self, client, tmp_path):
        # Register two clients
        client.post("/api/settings/client", json={"code": "CLA", "name": "Client A"})
        client.post("/api/settings/client", json={"code": "CLB", "name": "Client B"})
        # Create tickets for A
        client.post("/api/session/client", json={"code": "CLA"})
        client.post("/api/kanban/tickets", json={"title": "A Task 1"})
        client.post("/api/kanban/tickets", json={"title": "A Task 2"})
        # Create tickets for B
        client.post("/api/session/client", json={"code": "CLB"})
        client.post("/api/kanban/tickets", json={"title": "B Task 1"})
        # Check isolation - Client B sees only 1
        resp = client.get("/api/kanban/tickets")
        assert resp.json()["total"] == 1
        assert resp.json()["tickets"][0]["title"] == "B Task 1"
        # Switch to A - sees 2
        client.post("/api/session/client", json={"code": "CLA"})
        resp = client.get("/api/kanban/tickets")
        assert resp.json()["total"] == 2


class TestE2ETicketLifecycle:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch, register_client="TST")

    def test_ticket_full_lifecycle(self, client):
        # Create
        resp = client.post("/api/kanban/tickets", json={"title": "Lifecycle"})
        tid = resp.json()["id"]
        # Move through statuses
        for status in ["EN_PROGRESO", "TESTING", "ANALIZADO", "CERRADO"]:
            resp = client.put(f"/api/kanban/tickets/{tid}/move", json={"status": status})
            assert resp.status_code == 200
            assert resp.json()["status"] == status

    def test_ticket_lifecycle_history_recorded(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "History Track"})
        tid = resp.json()["id"]
        client.put(f"/api/kanban/tickets/{tid}/move", json={"status": "TESTING"})
        client.put(f"/api/kanban/tickets/{tid}/move", json={"status": "CERRADO"})
        resp = client.get(f"/api/kanban/tickets/{tid}/history")
        history = resp.json()
        assert len(history) == 3  # creation + 2 moves

    def test_ticket_lifecycle_closed_at_set(self, client):
        resp = client.post("/api/kanban/tickets", json={"title": "To Close"})
        tid = resp.json()["id"]
        resp = client.put(f"/api/kanban/tickets/{tid}/move", json={"status": "CERRADO"})
        assert resp.json()["closed_at"] is not None


class TestE2EExpenseWorkflow:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch)

    def _get_first_category_id(self, client):
        resp = client.get("/api/finance/categories")
        return resp.json()[0]["id"]

    def test_create_expense_then_export_csv(self, client):
        cat_id = self._get_first_category_id(client)
        for i, amount in enumerate([10.0, 20.0, 30.0], start=1):
            client.post("/api/finance/expenses", json={
                "period_year": 2025, "period_month": 1,
                "category_id": cat_id, "amount": amount,
                "merchant": f"Merchant{i}",
            })
        resp = client.get("/api/finance/expenses/export-csv?year=2025&month=1")
        assert resp.status_code == 200
        content = resp.text
        assert "Merchant1" in content
        assert "Merchant2" in content
        assert "Merchant3" in content

    def test_expense_with_document_upload(self, client):
        # Upload document
        resp = client.post(
            "/api/finance/upload",
            files={"file": ("receipt.pdf", b"fake pdf", "application/pdf")},
        )
        doc_id = resp.json()["id"]
        # Create expense linked to document
        cat_id = self._get_first_category_id(client)
        resp = client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 1,
            "category_id": cat_id, "amount": 42.50,
            "document_id": doc_id,
        })
        assert resp.status_code == 200
        assert resp.json()["document_id"] == doc_id

    def test_delete_document_unlinks_from_expense(self, client):
        resp = client.post(
            "/api/finance/upload",
            files={"file": ("r.pdf", b"pdf content", "application/pdf")},
        )
        doc_id = resp.json()["id"]
        cat_id = self._get_first_category_id(client)
        resp = client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 1,
            "category_id": cat_id, "amount": 20.0,
            "document_id": doc_id,
        })
        expense_id = resp.json()["id"]
        # Delete the document
        client.delete(f"/api/finance/documents/{doc_id}")
        # Expense should have document_id = null
        resp = client.get("/api/finance/expenses?year=2025&month=1")
        expenses = resp.json()["expenses"]
        target = next(e for e in expenses if e["id"] == expense_id)
        assert target["document_id"] is None


class TestE2EInvoiceWorkflow:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch)

    def test_create_invoice_with_items_generate_pdf(self, client):
        resp = client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 6,
            "client_name": "PDF Client", "invoice_number": "E2E-001",
            "vat_rate": 0.21,
            "items": [
                {"description": "Dev", "quantity": 40, "unit_price": 75.0, "unit": "HOURS"},
                {"description": "Design", "quantity": 16, "unit_price": 60.0, "unit": "HOURS"},
            ],
        })
        assert resp.status_code == 200
        invoice_id = resp.json()["id"]
        assert resp.json()["document_id"] is None
        # Generate PDF
        resp = client.post(f"/api/finance/invoices/{invoice_id}/generate-pdf")
        assert resp.status_code == 200
        doc_id = resp.json()["document_id"]
        assert doc_id is not None
        # Download PDF
        resp = client.get(f"/api/finance/documents/{doc_id}/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"

    def test_invoice_update_items_recalculates(self, client):
        resp = client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 1,
            "client_name": "Client", "invoice_number": "E2E-RECALC",
            "vat_rate": 0.10,
            "items": [{"description": "Old", "quantity": 5, "unit_price": 100.0, "unit": "HOURS"}],
        })
        invoice_id = resp.json()["id"]
        assert resp.json()["subtotal"] == 500.0
        # Replace items
        resp = client.put(f"/api/finance/invoices/{invoice_id}", json={
            "items": [
                {"description": "New A", "quantity": 10, "unit_price": 75.0, "unit": "HOURS"},
                {"description": "New B", "quantity": 5, "unit_price": 50.0, "unit": "DAYS"},
            ],
        })
        assert resp.status_code == 200
        assert resp.json()["subtotal"] == 1000.0
        assert resp.json()["vat_amount"] == 100.0
        assert resp.json()["total"] == 1100.0

    def test_invoice_csv_export_includes_all(self, client):
        for i in range(3):
            client.post("/api/finance/invoices", json={
                "period_year": 2025, "period_month": 1,
                "client_name": f"Client{i}", "invoice_number": f"CSV-{i}",
                "items": [{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
            })
        resp = client.get("/api/finance/invoices/export-csv?year=2025")
        assert resp.status_code == 200
        content = resp.text
        for i in range(3):
            assert f"Client{i}" in content
            assert f"CSV-{i}" in content


class TestE2EFinanceSummary:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch)

    def test_summary_reflects_invoices_and_expenses(self, client):
        # Create invoice (income)
        client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 3,
            "client_name": "Client", "invoice_number": "SUM-1",
            "items": [{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        })
        # Create expense
        cats_resp = client.get("/api/finance/categories")
        cat_id = cats_resp.json()[0]["id"]
        client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 3,
            "category_id": cat_id, "amount": 300.0,
        })
        resp = client.get("/api/finance/summary?year=2025&month=3")
        data = resp.json()
        m = data["months"][0]
        assert m["incomes"] == 1000.0
        assert m["expenses"] == 300.0
        assert m["profit"] == 700.0

    def test_summary_custom_tax_rate(self, client):
        resp = client.get("/api/finance/summary?year=2025&tax_rate=0.25")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["tax_rate"] == 0.25

    def test_summary_yearly_aggregation(self, client):
        resp = client.get("/api/finance/summary?year=2025")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["months"]) == 12
        assert "totals" in data


class TestE2EChatWorkflow:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch)

    def test_create_session_send_messages_export(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        session = repo.create_session(scope="general", title="E2E Chat")
        repo.add_message(session.session_id, role="user", content="What is SAP IS-U?")
        repo.add_message(session.session_id, role="assistant", content="SAP IS-U is a utility module.")
        # Export markdown
        md = repo.export_session_markdown(session.session_id)
        assert "# E2E Chat" in md
        assert "What is SAP IS-U?" in md
        assert "SAP IS-U is a utility module." in md

    def test_session_pin_survives_retention(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s1 = repo.create_session(scope="general", title="Pinned")
        s2 = repo.create_session(scope="general", title="Unpinned")
        repo.pin_session(s1.session_id, True)
        # Backdate both
        old_date = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        with sqlite3.connect(tmp_path / "chat.db") as conn:
            conn.execute("UPDATE chat_sessions SET last_message_at = ?", (old_date,))
            conn.commit()
        deleted = repo.cleanup_retention(retention_days=1)
        assert deleted == 1
        assert repo.get_session(s1.session_id) is not None  # pinned survives
        assert repo.get_session(s2.session_id) is None  # unpinned deleted

    def test_session_rename_then_search(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        s = repo.create_session(scope="general", title="Old Name")
        repo.rename_session(s.session_id, "Unique Search Term XYZ")
        results = repo.search_sessions("Unique Search Term XYZ")
        assert len(results) == 1
        assert results[0].session_id == s.session_id


class TestE2EMultiClientIsolation:
    def test_kanban_isolated_between_clients(self, tmp_path):
        cm = ClientManager(tmp_path)
        cm.register_client("A", "Client A")
        cm.register_client("B", "Client B")
        repo_a = KanbanRepository(tmp_path / "clients" / "A" / "kanban.sqlite", seed_columns=False)
        repo_b = KanbanRepository(tmp_path / "clients" / "B" / "kanban.sqlite", seed_columns=False)
        repo_a.create_ticket(title="A Only")
        assert len(repo_a.list_tickets()) == 1
        assert len(repo_b.list_tickets()) == 0

    def test_kb_isolated_between_clients(self, tmp_path):
        cm = ClientManager(tmp_path)
        cm.register_client("A", "Client A")
        cm.register_client("B", "Client B")
        kb_a = KBItemRepository(tmp_path / "clients" / "A" / "assistant_kb.sqlite")
        kb_b = KBItemRepository(tmp_path / "clients" / "B" / "assistant_kb.sqlite")
        kb_a.create_or_update(
            client_scope="client", client_code="A",
            item_type=KBItemType.GLOSSARY, title="A Item",
            content_markdown="C", tags=[], sap_objects=[], signals={}, sources={},
        )
        assert len(kb_a.list_by_scope("client", client_code="A")) == 1
        assert len(kb_b.list_by_scope("client", client_code="B")) == 0

    def test_finance_is_global(self, tmp_path):
        repo = FinanceRepository(tmp_path / "finance.sqlite")
        cats = repo.list_categories()
        repo.create_expense(period_year=2025, period_month=1,
                            category_id=cats[0].id, amount=100.0)
        # Same repo, same data - finance is not per-client
        repo2 = FinanceRepository(tmp_path / "finance.sqlite")
        assert repo2.count_expenses() == 1

    def test_chat_sessions_global(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.sqlite")
        repo.create_session(scope="general", title="Global Session")
        repo2 = ChatRepository(tmp_path / "chat.sqlite")
        sessions = repo2.list_sessions()
        assert len(sessions) == 1


# ════════════════════════════════════════════════════════════════
# Section 11: Data Validation Tests
# ════════════════════════════════════════════════════════════════


class TestInputValidation:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        return _make_api_client(tmp_path, monkeypatch, register_client="TST")

    def test_kanban_create_missing_title(self, client):
        resp = client.post("/api/kanban/tickets", json={})
        assert resp.status_code == 400

    def test_kanban_create_very_long_title(self, client):
        long_title = "A" * 10000
        resp = client.post("/api/kanban/tickets", json={"title": long_title})
        assert resp.status_code == 200  # No length limit in current code
        assert resp.json()["title"] == long_title

    def test_kanban_search_sql_injection_attempt(self, client):
        """SQL injection attempt should be handled safely by parameterized queries."""
        client.post("/api/kanban/tickets", json={"title": "Normal Ticket"})
        resp = client.get("/api/kanban/tickets?search='; DROP TABLE tickets;--")
        assert resp.status_code == 200
        # The original ticket should still exist
        resp2 = client.get("/api/kanban/tickets")
        assert resp2.json()["total"] >= 1

    def test_finance_settings_high_tax_rate(self, tmp_path, monkeypatch):
        c = _make_api_client(tmp_path, monkeypatch)
        resp = c.put("/api/finance/settings", json={"tax_rate_default": 2.0})
        assert resp.status_code == 200
        # No validation cap - stores 200%
        assert resp.json()["tax_rate_default"] == 2.0

    def test_settings_invalid_qdrant_url_stored(self, tmp_path, monkeypatch):
        c = _make_api_client(tmp_path, monkeypatch)
        resp = c.post("/api/settings/qdrant", json={"url": "not-a-url"})
        assert resp.status_code == 200
        assert resp.json()["qdrant_url"] == "not-a-url"

    def test_finance_upload_empty_file(self, tmp_path, monkeypatch):
        c = _make_api_client(tmp_path, monkeypatch)
        resp = c.post(
            "/api/finance/upload",
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.json()["size_bytes"] == 0

    def test_kanban_duplicate_ticket_id_rejects(self, client):
        client.post("/api/kanban/tickets", json={"title": "First", "ticket_id": "DUP-001"})
        resp = client.post("/api/kanban/tickets", json={"title": "Second", "ticket_id": "DUP-001"})
        assert resp.status_code == 400

    def test_finance_create_expense_missing_field(self, tmp_path, monkeypatch):
        c = _make_api_client(tmp_path, monkeypatch)
        resp = c.post("/api/finance/expenses", json={"period_year": 2025})
        assert resp.status_code == 400

    def test_finance_create_invoice_missing_field(self, tmp_path, monkeypatch):
        c = _make_api_client(tmp_path, monkeypatch)
        resp = c.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 6,
            "client_name": "Client",
            # missing invoice_number
        })
        assert resp.status_code == 400


# ════════════════════════════════════════════════════════════════
# Section 12: Error Handling Tests
# ════════════════════════════════════════════════════════════════


class TestErrorHandling:
    def test_finance_repo_creates_parent_dirs(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "c" / "fin.db"
        repo = FinanceRepository(deep_path)
        assert deep_path.parent.is_dir()
        s = repo.get_settings()
        assert s is not None

    def test_kanban_repo_creates_without_error(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        cols = repo.list_columns()
        assert len(cols) == len(DEFAULT_COLUMNS)

    def test_chat_repo_creates_parent_dirs(self, tmp_path):
        deep_path = tmp_path / "x" / "y" / "chat.db"
        repo = ChatRepository(deep_path)
        session = repo.create_session(scope="general")
        assert session is not None

    def test_delete_nonexistent_expense(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        assert repo.delete_expense("nonexistent") is False

    def test_delete_nonexistent_invoice(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        assert repo.delete_invoice("nonexistent") is False

    def test_delete_nonexistent_document(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        assert repo.delete_document("nonexistent") is False

    def test_delete_nonexistent_ticket(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        assert repo.delete_ticket("nonexistent") is False

    def test_delete_nonexistent_session(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        assert repo.delete_session("nonexistent") is False

    def test_get_nonexistent_invoice(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        assert repo.get_invoice("nonexistent") is None

    def test_get_nonexistent_expense(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        assert repo.get_expense("nonexistent") is None

    def test_get_nonexistent_document(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        assert repo.get_document("nonexistent") is None

    def test_finance_delete_category_with_expenses(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        repo.create_expense(period_year=2025, period_month=1,
                            category_id=cats[0].id, amount=10.0)
        with pytest.raises(ValueError, match="expense"):
            repo.delete_category(cats[0].id)

    def test_kanban_delete_column_with_tickets(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        repo.create_ticket(title="Blocker", status="EN_PROGRESO")
        cols = repo.list_columns()
        en_progreso = next(c for c in cols if c.name == "EN_PROGRESO")
        with pytest.raises(ValueError, match="ticket"):
            repo.delete_column(en_progreso.id)

    def test_chat_export_nonexistent_session(self, tmp_path):
        repo = ChatRepository(tmp_path / "chat.db")
        assert repo.export_session_markdown("nonexistent") is None
        assert repo.export_session_json("nonexistent") is None

    def test_update_nonexistent_ticket_status(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        assert repo.update_status("nonexistent", "TESTING") is None

    def test_update_nonexistent_ticket_fields(self, tmp_path):
        repo = KanbanRepository(tmp_path / "k.db", seed_columns=True)
        assert repo.update_ticket("nonexistent", title="New") is None

    def test_ingestion_repo_creates_and_retrieves(self, tmp_path):
        db_path = tmp_path / "kb.db"
        repo = IngestionRepository(db_path)
        ing = repo.create(
            client_scope="standard", client_code=None,
            input_kind="text", input_hash="abc123",
            input_name="test.txt", model_used="gpt-5.2",
            reasoning_effort="xhigh",
        )
        assert ing.ingestion_id is not None
        assert ing.status == "DRAFT"
        fetched = repo.get_by_id(ing.ingestion_id)
        assert fetched.input_kind == "text"

    def test_ingestion_repo_update_status(self, tmp_path):
        repo = IngestionRepository(tmp_path / "kb.db")
        ing = repo.create(
            client_scope="standard", client_code=None,
            input_kind="pdf", input_hash="def456",
            input_name="doc.pdf", model_used="gpt-5.2",
            reasoning_effort="xhigh",
        )
        updated = repo.update_status(ing.ingestion_id, IngestionStatus.SYNTHESIZED)
        assert updated.status == "SYNTHESIZED"

    def test_ingestion_repo_list_by_scope(self, tmp_path):
        repo = IngestionRepository(tmp_path / "kb.db")
        repo.create(
            client_scope="standard", client_code=None,
            input_kind="text", input_hash="h1",
            input_name="a.txt", model_used="gpt-5.2",
            reasoning_effort="xhigh",
        )
        repo.create(
            client_scope="client", client_code="TST",
            input_kind="text", input_hash="h2",
            input_name="b.txt", model_used="gpt-5.2",
            reasoning_effort="xhigh",
        )
        std = repo.list_by_scope("standard")
        assert len(std) == 1
        client_items = repo.list_by_scope("client", client_code="TST")
        assert len(client_items) == 1
