"""
UI module tests: verify imports, app state, and wiring.

No Tk display needed - tests only verify module structure and non-GUI logic.
"""
from pathlib import Path

import pytest


def test_ui_imports():
    """Test all UI modules import without error."""
    from src.ui.app import SapAssistantApp, main
    from src.ui.tabs.chat_tab import ChatTab
    from src.ui.tabs.ingest_tab import IngestTab
    from src.ui.tabs.review_tab import ReviewTab
    from src.ui.tabs.kanban_tab import KanbanTab
    from src.ui.tabs.settings_tab import SettingsTab


def test_app_state():
    """Test AppState dataclass."""
    from src.shared.app_state import AppState

    state = AppState(data_root=Path("/tmp/test"))
    assert state.data_root == Path("/tmp/test")
    assert state.active_client_code is None
    assert state.standard_kb_enabled is True
    assert state.qdrant_url == "http://localhost:6333"

    state.active_client_code = "SWE"
    assert state.active_client_code == "SWE"

    state.standard_kb_enabled = False
    assert state.standard_kb_enabled is False


def test_chat_context_pack_building():
    """Test context pack building logic (no GUI)."""
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


def test_kanban_columns_defined():
    """Test kanban column constants match TicketStatus."""
    from src.ui.tabs.kanban_tab import COLUMNS
    from src.kanban.storage.kanban_repository import TicketStatus

    assert "OPEN" in COLUMNS
    assert "IN_PROGRESS" in COLUMNS
    assert "WAITING" in COLUMNS
    assert "DONE" in COLUMNS
