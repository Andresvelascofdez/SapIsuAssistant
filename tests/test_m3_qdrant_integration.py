"""
M3 Acceptance Tests: Qdrant Integration (Collections + Upsert + Search)

Tests verify Qdrant integration per PLAN.md section 4.
Uses mocks to avoid dependency on Docker during CI per PLAN.md section 13.
"""
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.assistant.retrieval.qdrant_service import QdrantService
from src.assistant.storage.models import KBItem


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client."""
    with patch("src.assistant.retrieval.qdrant_service.QdrantClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


def test_qdrant_service_initialization(mock_qdrant_client):
    """Test Qdrant service initializes with correct URL."""
    service = QdrantService("http://test:6333")
    assert service.client == mock_qdrant_client


def test_get_collection_name_standard(mock_qdrant_client):
    """Test collection name for standard scope."""
    service = QdrantService()
    name = service._get_collection_name("standard", None)
    assert name == "kb_standard"


def test_get_collection_name_client(mock_qdrant_client):
    """Test collection name for client scope."""
    service = QdrantService()
    name = service._get_collection_name("client", "SWE")
    assert name == "kb_SWE"


def test_get_collection_name_client_uppercase(mock_qdrant_client):
    """Test collection name normalizes client code to uppercase."""
    service = QdrantService()
    name = service._get_collection_name("client", "swe")
    assert name == "kb_SWE"


def test_get_collection_name_invalid_scope(mock_qdrant_client):
    """Test invalid scope raises error."""
    service = QdrantService()
    with pytest.raises(ValueError, match="Invalid client_scope"):
        service._get_collection_name("invalid", None)


def test_get_collection_name_client_without_code(mock_qdrant_client):
    """Test client scope without code raises error."""
    service = QdrantService()
    with pytest.raises(ValueError, match="client_code required"):
        service._get_collection_name("client", None)


def test_ensure_collection_exists_creates_if_missing(mock_qdrant_client):
    """Test collection is created if it doesn't exist per PLAN.md section 4.1."""
    mock_qdrant_client.collection_exists.return_value = False

    service = QdrantService()
    service.ensure_collection_exists("standard", None)

    # Verify collection was created with correct parameters
    mock_qdrant_client.create_collection.assert_called_once()
    call_args = mock_qdrant_client.create_collection.call_args

    assert call_args[1]["collection_name"] == "kb_standard"
    # Vector config should be 3072 dimensions, cosine distance
    assert call_args[1]["vectors_config"].size == 3072
    assert call_args[1]["vectors_config"].distance.name == "COSINE"


def test_ensure_collection_exists_skips_if_exists(mock_qdrant_client):
    """Test collection creation is skipped if exists with correct dimensions."""
    mock_qdrant_client.collection_exists.return_value = True

    # Mock get_collection to return correct vector size
    mock_info = Mock()
    mock_info.config.params.vectors.size = 3072
    mock_qdrant_client.get_collection.return_value = mock_info

    service = QdrantService()
    service.ensure_collection_exists("standard", None)

    # Verify collection was not created
    mock_qdrant_client.create_collection.assert_not_called()


def test_upsert_kb_item_approved(mock_qdrant_client):
    """Test upserting APPROVED KB item per PLAN.md section 4.5."""
    mock_qdrant_client.collection_exists.return_value = True

    # Mock get_collection to return correct vector size
    mock_info = Mock()
    mock_info.config.params.vectors.size = 3072
    mock_qdrant_client.get_collection.return_value = mock_info

    kb_item = KBItem(
        kb_id="test-id-123",
        client_scope="standard",
        client_code=None,
        type="RUNBOOK",
        title="Test Runbook",
        content_markdown="# Content",
        tags_json='["tag1", "tag2"]',
        sap_objects_json='["OBJ1"]',
        signals_json='{}',
        sources_json='{}',
        version=1,
        status="APPROVED",  # Must be APPROVED
        content_hash="hash123",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )

    embedding = [0.1] * 3072  # 3072 dimensions

    service = QdrantService()
    service.upsert_kb_item(kb_item, embedding)

    # Verify upsert was called
    mock_qdrant_client.upsert.assert_called_once()
    call_args = mock_qdrant_client.upsert.call_args

    assert call_args[1]["collection_name"] == "kb_standard"
    points = call_args[1]["points"]
    assert len(points) == 1

    point = points[0]
    assert point.id == "test-id-123"
    assert point.vector == embedding
    assert point.payload["kb_id"] == "test-id-123"
    assert point.payload["type"] == "RUNBOOK"
    assert point.payload["title"] == "Test Runbook"
    assert point.payload["tags"] == ["tag1", "tag2"]
    assert point.payload["sap_objects"] == ["OBJ1"]
    assert point.payload["version"] == 1


def test_upsert_kb_item_not_approved_raises_error(mock_qdrant_client):
    """Test upserting non-APPROVED item raises error per PLAN.md section 4.5."""
    kb_item = KBItem(
        kb_id="test-id",
        client_scope="standard",
        client_code=None,
        type="RUNBOOK",
        title="Test",
        content_markdown="# Content",
        tags_json="[]",
        sap_objects_json="[]",
        signals_json="{}",
        sources_json="{}",
        version=1,
        status="DRAFT",  # Not APPROVED
        content_hash="hash",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )

    embedding = [0.1] * 3072

    service = QdrantService()

    with pytest.raises(ValueError, match="Only APPROVED items"):
        service.upsert_kb_item(kb_item, embedding)


def test_upsert_kb_item_wrong_embedding_size_raises_error(mock_qdrant_client):
    """Test upserting with wrong embedding size raises error."""
    kb_item = KBItem(
        kb_id="test-id",
        client_scope="standard",
        client_code=None,
        type="RUNBOOK",
        title="Test",
        content_markdown="# Content",
        tags_json="[]",
        sap_objects_json="[]",
        signals_json="{}",
        sources_json="{}",
        version=1,
        status="APPROVED",
        content_hash="hash",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )

    wrong_embedding = [0.1] * 1536  # Wrong size (should be 3072)

    service = QdrantService()

    with pytest.raises(ValueError, match="must be 3072 dimensions"):
        service.upsert_kb_item(kb_item, wrong_embedding)


def test_search_standard_only(mock_qdrant_client):
    """Test searching standard collection only."""
    mock_qdrant_client.collection_exists.return_value = True

    # Mock search results
    mock_hit1 = Mock()
    mock_hit1.payload = {"kb_id": "kb1"}
    mock_hit1.score = 0.95

    mock_hit2 = Mock()
    mock_hit2.payload = {"kb_id": "kb2"}
    mock_hit2.score = 0.90

    mock_qdrant_client.search.return_value = [mock_hit1, mock_hit2]

    service = QdrantService()
    query_embedding = [0.2] * 3072

    results = service.search(
        query_embedding=query_embedding,
        client_scope="standard",
        client_code=None,
        limit=8,
        include_standard=True,
    )

    # Verify search was called on kb_standard
    mock_qdrant_client.search.assert_called_once()
    call_args = mock_qdrant_client.search.call_args
    assert call_args[1]["collection_name"] == "kb_standard"
    assert call_args[1]["query_vector"] == query_embedding
    assert call_args[1]["limit"] == 8

    # Verify results
    assert len(results) == 2
    assert results[0] == ("kb1", 0.95)
    assert results[1] == ("kb2", 0.90)


def test_search_client_with_standard(mock_qdrant_client):
    """Test searching client + standard collections per PLAN.md section 4.6."""
    def collection_exists_side_effect(collection_name):
        return collection_name in ["kb_standard", "kb_SWE"]

    mock_qdrant_client.collection_exists.side_effect = collection_exists_side_effect

    # Mock search results for standard
    mock_standard_hit = Mock()
    mock_standard_hit.payload = {"kb_id": "std-kb1"}
    mock_standard_hit.score = 0.90

    # Mock search results for client
    mock_client_hit = Mock()
    mock_client_hit.payload = {"kb_id": "swe-kb1"}
    mock_client_hit.score = 0.95

    def search_side_effect(**kwargs):
        if kwargs["collection_name"] == "kb_standard":
            return [mock_standard_hit]
        elif kwargs["collection_name"] == "kb_SWE":
            return [mock_client_hit]
        return []

    mock_qdrant_client.search.side_effect = search_side_effect

    service = QdrantService()
    query_embedding = [0.2] * 3072

    results = service.search(
        query_embedding=query_embedding,
        client_scope="client",
        client_code="SWE",
        limit=8,
        include_standard=True,
    )

    # Verify both collections were queried
    assert mock_qdrant_client.search.call_count == 2

    # Verify results are merged and sorted by score (descending)
    assert len(results) <= 8
    assert results[0] == ("swe-kb1", 0.95)  # Higher score first
    assert results[1] == ("std-kb1", 0.90)


def test_search_client_without_standard(mock_qdrant_client):
    """Test searching only client collection (standard disabled)."""
    mock_qdrant_client.collection_exists.return_value = True

    mock_hit = Mock()
    mock_hit.payload = {"kb_id": "kb1"}
    mock_hit.score = 0.95

    mock_qdrant_client.search.return_value = [mock_hit]

    service = QdrantService()
    query_embedding = [0.2] * 3072

    results = service.search(
        query_embedding=query_embedding,
        client_scope="client",
        client_code="SWE",
        limit=8,
        include_standard=False,  # Standard disabled
    )

    # Verify only client collection was queried
    mock_qdrant_client.search.assert_called_once()
    call_args = mock_qdrant_client.search.call_args
    assert call_args[1]["collection_name"] == "kb_SWE"

    assert len(results) == 1
    assert results[0] == ("kb1", 0.95)


def test_search_wrong_embedding_size_raises_error(mock_qdrant_client):
    """Test searching with wrong embedding size raises error."""
    service = QdrantService()
    wrong_embedding = [0.2] * 1536

    with pytest.raises(ValueError, match="must be 3072 dimensions"):
        service.search(
            query_embedding=wrong_embedding,
            client_scope="standard",
            client_code=None,
        )


def test_delete_kb_item(mock_qdrant_client):
    """Test deleting KB item from Qdrant."""
    mock_qdrant_client.collection_exists.return_value = True

    kb_item = KBItem(
        kb_id="test-id-123",
        client_scope="standard",
        client_code=None,
        type="RUNBOOK",
        title="Test",
        content_markdown="# Content",
        tags_json="[]",
        sap_objects_json="[]",
        signals_json="{}",
        sources_json="{}",
        version=1,
        status="APPROVED",
        content_hash="hash",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )

    service = QdrantService()
    service.delete_kb_item(kb_item)

    # Verify delete was called
    mock_qdrant_client.delete.assert_called_once()
    call_args = mock_qdrant_client.delete.call_args
    assert call_args[1]["collection_name"] == "kb_standard"
    assert call_args[1]["points_selector"] == ["test-id-123"]
