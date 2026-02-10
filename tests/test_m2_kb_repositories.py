"""
M2 Acceptance Tests: Assistant SQLite Repos + KB Item CRUD + Dedupe + Versioning

Tests verify dedupe and version increment rules per PLAN.md section 5.1.
"""
import json

import pytest

from src.assistant.storage.ingestion_repository import IngestionRepository
from src.assistant.storage.kb_repository import KBItemRepository
from src.assistant.storage.models import IngestionStatus, KBItemStatus, KBItemType


def test_kb_repository_init_creates_schema(tmp_path):
    """Test KB repository initializes schema correctly."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = KBItemRepository(db_path)

    assert db_path.exists()

    # Verify table exists
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kb_items'"
        )
        assert cursor.fetchone() is not None


def test_create_kb_item_new(tmp_path):
    """Test creating a new KB item."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = KBItemRepository(db_path)

    item, is_new = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="Test Runbook",
        content_markdown="# Test content",
        tags=["test", "runbook"],
        sap_objects=["OBJ1", "OBJ2"],
        signals={"module": "IDEX"},
        sources={"file": "test.pdf"},
        status=KBItemStatus.DRAFT,
    )

    assert is_new is True
    assert item.kb_id
    assert item.type == "RUNBOOK"
    assert item.title == "Test Runbook"
    assert item.content_markdown == "# Test content"
    assert item.version == 1
    assert item.status == "DRAFT"
    assert item.client_scope == "standard"
    assert item.client_code is None

    # Verify tags and sap_objects are JSON
    tags = json.loads(item.tags_json)
    assert tags == ["test", "runbook"]

    sap_objects = json.loads(item.sap_objects_json)
    assert sap_objects == ["OBJ1", "OBJ2"]


def test_dedupe_same_content_returns_existing(tmp_path):
    """
    Test dedupe rule: same type + title + content_hash -> return existing.

    Per PLAN.md section 5.1: If same type + normalized_title and same content_hash
    exists in same scope, do not create duplicate.
    """
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = KBItemRepository(db_path)

    # Create first item
    item1, is_new1 = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="Test Runbook",
        content_markdown="# Test content",
        tags=["test"],
        sap_objects=["OBJ1"],
        signals={},
        sources={},
    )

    assert is_new1 is True
    assert item1.version == 1

    # Try to create same item again (same type, title, content)
    item2, is_new2 = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="Test Runbook",  # Same title
        content_markdown="# Test content",  # Same content
        tags=["different", "tags"],  # Different tags (doesn't matter for dedupe)
        sap_objects=["DIFFERENT"],  # Different objects (doesn't matter)
        signals={},
        sources={},
    )

    # Should return existing item
    assert is_new2 is False
    assert item2.kb_id == item1.kb_id
    assert item2.version == 1
    assert item2.content_hash == item1.content_hash


def test_dedupe_title_case_insensitive(tmp_path):
    """Test dedupe treats titles as case-insensitive."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = KBItemRepository(db_path)

    # Create first item
    item1, is_new1 = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="Test Runbook",
        content_markdown="# Content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    # Same item with different title case
    item2, is_new2 = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="TEST RUNBOOK",  # Different case
        content_markdown="# Content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    # Should return existing (case-insensitive dedupe)
    assert is_new2 is False
    assert item2.kb_id == item1.kb_id


def test_versioning_different_content_increments_version(tmp_path):
    """
    Test versioning rule: same type + title + different content_hash -> new version.

    Per PLAN.md section 5.1: If same type + normalized_title but different content_hash,
    create a new version (increment version).
    """
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = KBItemRepository(db_path)

    # Create first version
    item1, is_new1 = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="Test Runbook",
        content_markdown="# Version 1 content",
        tags=["v1"],
        sap_objects=[],
        signals={},
        sources={},
    )

    assert is_new1 is True
    assert item1.version == 1
    original_kb_id = item1.kb_id

    # Update with different content (same type + title)
    item2, is_new2 = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="Test Runbook",  # Same title
        content_markdown="# Version 2 content - DIFFERENT",  # Different content
        tags=["v2"],
        sap_objects=[],
        signals={},
        sources={},
    )

    # Should be an update (not new), version incremented
    assert is_new2 is False
    assert item2.kb_id == original_kb_id  # Same ID
    assert item2.version == 2  # Incremented
    assert item2.content_hash != item1.content_hash

    # Third version
    item3, is_new3 = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="test runbook",  # Case insensitive
        content_markdown="# Version 3 content - NEW AGAIN",
        tags=["v3"],
        sap_objects=[],
        signals={},
        sources={},
    )

    assert is_new3 is False
    assert item3.kb_id == original_kb_id
    assert item3.version == 3


def test_different_type_creates_separate_item(tmp_path):
    """Test different type creates separate item even with same title."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = KBItemRepository(db_path)

    # Create RUNBOOK
    item1, is_new1 = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="Common Title",
        content_markdown="# Content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    # Create GLOSSARY with same title
    item2, is_new2 = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.GLOSSARY,  # Different type
        title="Common Title",  # Same title
        content_markdown="# Content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    # Should be separate items
    assert is_new2 is True
    assert item2.kb_id != item1.kb_id
    assert item2.version == 1


def test_client_scope_isolation(tmp_path):
    """Test KB items are isolated by client scope."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = KBItemRepository(db_path)

    # Create in standard scope
    item1, _ = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="Shared Title",
        content_markdown="# Standard content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    # Create in client scope (same title, same content)
    item2, is_new2 = repo.create_or_update(
        client_scope="client",
        client_code="SWE",
        item_type=KBItemType.RUNBOOK,
        title="Shared Title",
        content_markdown="# Standard content",  # Same content
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    # Should be separate items (different scope)
    assert is_new2 is True
    assert item2.kb_id != item1.kb_id
    assert item2.client_scope == "client"
    assert item2.client_code == "SWE"


def test_list_by_scope_standard(tmp_path):
    """Test listing KB items by standard scope."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = KBItemRepository(db_path)

    # Create items in different scopes
    repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="Standard 1",
        content_markdown="# Content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.GLOSSARY,
        title="Standard 2",
        content_markdown="# Content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    repo.create_or_update(
        client_scope="client",
        client_code="SWE",
        item_type=KBItemType.RUNBOOK,
        title="Client Item",
        content_markdown="# Content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    # List standard items only
    standard_items = repo.list_by_scope("standard", None)
    assert len(standard_items) == 2
    assert all(item.client_scope == "standard" for item in standard_items)


def test_list_by_scope_client(tmp_path):
    """Test listing KB items by client scope."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = KBItemRepository(db_path)

    repo.create_or_update(
        client_scope="client",
        client_code="SWE",
        item_type=KBItemType.RUNBOOK,
        title="SWE Item",
        content_markdown="# Content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    repo.create_or_update(
        client_scope="client",
        client_code="HERON",
        item_type=KBItemType.RUNBOOK,
        title="HERON Item",
        content_markdown="# Content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
    )

    # List SWE items only
    swe_items = repo.list_by_scope("client", "SWE")
    assert len(swe_items) == 1
    assert swe_items[0].client_code == "SWE"


def test_update_status(tmp_path):
    """Test updating KB item status."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = KBItemRepository(db_path)

    item, _ = repo.create_or_update(
        client_scope="standard",
        client_code=None,
        item_type=KBItemType.RUNBOOK,
        title="Test",
        content_markdown="# Content",
        tags=[],
        sap_objects=[],
        signals={},
        sources={},
        status=KBItemStatus.DRAFT,
    )

    assert item.status == "DRAFT"

    # Update to APPROVED
    updated = repo.update_status(item.kb_id, KBItemStatus.APPROVED)
    assert updated.status == "APPROVED"
    assert updated.kb_id == item.kb_id


def test_ingestion_repository_init_creates_schema(tmp_path):
    """Test ingestion repository initializes schema correctly."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = IngestionRepository(db_path)

    assert db_path.exists()

    import sqlite3
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ingestions'"
        )
        assert cursor.fetchone() is not None


def test_create_ingestion(tmp_path):
    """Test creating ingestion record."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = IngestionRepository(db_path)

    ingestion = repo.create(
        client_scope="standard",
        client_code=None,
        input_kind="pdf",
        input_hash="abc123",
        input_name="test.pdf",
        model_used="gpt-5.2",
        reasoning_effort="xhigh",
        status=IngestionStatus.SYNTHESIZED,
    )

    assert ingestion.ingestion_id
    assert ingestion.input_kind == "pdf"
    assert ingestion.input_hash == "abc123"
    assert ingestion.status == "SYNTHESIZED"


def test_ingestion_update_status(tmp_path):
    """Test updating ingestion status."""
    db_path = tmp_path / "assistant_kb.sqlite"
    repo = IngestionRepository(db_path)

    ingestion = repo.create(
        client_scope="standard",
        client_code=None,
        input_kind="text",
        input_hash="hash123",
        input_name=None,
        model_used="gpt-5.2",
        reasoning_effort="xhigh",
        status=IngestionStatus.DRAFT,
    )

    assert ingestion.status == "DRAFT"

    updated = repo.update_status(ingestion.ingestion_id, IngestionStatus.APPROVED)
    assert updated.status == "APPROVED"
