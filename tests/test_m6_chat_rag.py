"""
M6 Acceptance Tests: Assistant Chat RAG

Tests ensure only standard + active client collections queried per PLAN.md section 10.
"""
import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.assistant.chat.chat_service import ChatResult, ChatService
from src.assistant.retrieval.embedding_service import EmbeddingService
from src.assistant.storage.models import KBItem


def _make_kb_item(kb_id: str, title: str, scope: str = "standard", client_code=None):
    """Helper to create test KB items."""
    return KBItem(
        kb_id=kb_id,
        client_scope=scope,
        client_code=client_code,
        type="RUNBOOK",
        title=title,
        content_markdown=f"# {title}\n\nContent for {title}",
        tags_json='["SAP", "IS-U"]',
        sap_objects_json='["SE38"]',
        signals_json='{"module": "IDEX"}',
        sources_json="{}",
        version=1,
        status="APPROVED",
        content_hash="hash",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )


@pytest.fixture
def mock_embedding_service():
    service = MagicMock(spec=EmbeddingService)
    service.embed.return_value = [0.1] * 3072
    return service


@pytest.fixture
def mock_qdrant_service():
    from src.assistant.retrieval.qdrant_service import QdrantService
    service = MagicMock(spec=QdrantService)
    return service


@pytest.fixture
def mock_kb_repo():
    from src.assistant.storage.kb_repository import KBItemRepository
    repo = MagicMock(spec=KBItemRepository)
    return repo


@patch("src.assistant.chat.chat_service.OpenAI")
def test_chat_ancliar_standard_scope(mock_openai_class, mock_embedding_service, mock_qdrant_service, mock_kb_repo):
    """Test chat ancliar with standard scope."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    # Setup search results
    mock_qdrant_service.search.return_value = [("kb1", 0.95), ("kb2", 0.90)]

    # Setup KB items
    item1 = _make_kb_item("kb1", "IDEX Monitoring")
    item2 = _make_kb_item("kb2", "UTILMD Processing")
    mock_kb_repo.get_by_id.side_effect = lambda kb_id: {"kb1": item1, "kb2": item2}.get(kb_id)

    # Setup OpenAI response
    response = Mock()
    response.output_text = "Based on the context, here is the ancliar."
    mock_client.responses.create.return_value = response

    chat = ChatService(
        embedding_service=mock_embedding_service,
        qdrant_service=mock_qdrant_service,
        api_key="test-key",
    )

    result = chat.ancliar(
        question="How to monitor IDEX?",
        kb_repo=mock_kb_repo,
        client_scope="standard",
        client_code=None,
        include_standard=True,
    )

    assert isinstance(result, ChatResult)
    assert result.ancliar == "Based on the context, here is the ancliar."
    assert len(result.sources) == 2
    assert result.sources[0].kb_id == "kb1"

    # Verify embedding was called
    mock_embedding_service.embed.assert_called_once_with("How to monitor IDEX?")

    # Verify search was called with correct params
    mock_qdrant_service.search.assert_called_once_with(
        query_embedding=[0.1] * 3072,
        client_scope="standard",
        client_code=None,
        limit=8,
        include_standard=True,
    )


@patch("src.assistant.chat.chat_service.OpenAI")
def test_chat_ancliar_client_scope_with_standard(mock_openai_class, mock_embedding_service, mock_qdrant_service, mock_kb_repo):
    """Test chat queries both standard + active client per PLAN.md section 10.1."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_qdrant_service.search.return_value = [("std1", 0.88), ("clia1", 0.95)]

    std_item = _make_kb_item("std1", "Standard KB Item", "standard")
    clia_item = _make_kb_item("clia1", "CLIA Client Item", "client", "CLIA")
    mock_kb_repo.get_by_id.side_effect = lambda kb_id: {"std1": std_item, "clia1": clia_item}.get(kb_id)

    response = Mock()
    response.output_text = "Ancliar using both standard and client knowledge."
    mock_client.responses.create.return_value = response

    chat = ChatService(
        embedding_service=mock_embedding_service,
        qdrant_service=mock_qdrant_service,
        api_key="test-key",
    )

    result = chat.ancliar(
        question="GPKE process",
        kb_repo=mock_kb_repo,
        client_scope="client",
        client_code="CLIA",
        include_standard=True,
    )

    # Verify search queries standard + client
    mock_qdrant_service.search.assert_called_once_with(
        query_embedding=[0.1] * 3072,
        client_scope="client",
        client_code="CLIA",
        limit=8,
        include_standard=True,
    )

    assert len(result.sources) == 2


@patch("src.assistant.chat.chat_service.OpenAI")
def test_chat_ancliar_client_without_standard(mock_openai_class, mock_embedding_service, mock_qdrant_service, mock_kb_repo):
    """Test chat queries only client collection when standard disabled."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_qdrant_service.search.return_value = [("clia1", 0.92)]
    clia_item = _make_kb_item("clia1", "CLIA Only Item", "client", "CLIA")
    mock_kb_repo.get_by_id.side_effect = lambda kb_id: {"clia1": clia_item}.get(kb_id)

    response = Mock()
    response.output_text = "Ancliar from client KB only."
    mock_client.responses.create.return_value = response

    chat = ChatService(
        embedding_service=mock_embedding_service,
        qdrant_service=mock_qdrant_service,
        api_key="test-key",
    )

    result = chat.ancliar(
        question="Client question",
        kb_repo=mock_kb_repo,
        client_scope="client",
        client_code="CLIA",
        include_standard=False,
    )

    mock_qdrant_service.search.assert_called_once_with(
        query_embedding=[0.1] * 3072,
        client_scope="client",
        client_code="CLIA",
        limit=8,
        include_standard=False,
    )


@patch("src.assistant.chat.chat_service.OpenAI")
def test_chat_no_results(mock_openai_class, mock_embedding_service, mock_qdrant_service, mock_kb_repo):
    """Test chat with no search results."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_qdrant_service.search.return_value = []

    response = Mock()
    response.output_text = "No relevant knowledge found."
    mock_client.responses.create.return_value = response

    chat = ChatService(
        embedding_service=mock_embedding_service,
        qdrant_service=mock_qdrant_service,
        api_key="test-key",
    )

    result = chat.ancliar(
        question="Unknown topic",
        kb_repo=mock_kb_repo,
        client_scope="standard",
        client_code=None,
    )

    assert result.sources == []
    assert result.ancliar == "No relevant knowledge found."


@patch("src.assistant.chat.chat_service.OpenAI")
def test_chat_reasoning_effort_xhigh(mock_openai_class, mock_embedding_service, mock_qdrant_service, mock_kb_repo):
    """Test chat supports xhigh reasoning effort per PLAN.md section 10.2."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_qdrant_service.search.return_value = []

    response = Mock()
    response.output_text = "Deep analysis ancliar."
    mock_client.responses.create.return_value = response

    chat = ChatService(
        embedding_service=mock_embedding_service,
        qdrant_service=mock_qdrant_service,
        api_key="test-key",
    )

    chat.ancliar(
        question="Complex question",
        kb_repo=mock_kb_repo,
        client_scope="standard",
        client_code=None,
        reasoning_effort="xhigh",
    )

    # Verify reasoning effort was passed
    call_kwargs = mock_client.responses.create.call_args[1]
    assert call_kwargs["reasoning"] == {"effort": "xhigh"}


@patch("src.assistant.chat.chat_service.OpenAI")
def test_chat_traceability(mock_openai_class, mock_embedding_service, mock_qdrant_service, mock_kb_repo):
    """Test traceability: KB items used are returned per PLAN.md section 10.3."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_qdrant_service.search.return_value = [("kb1", 0.9), ("kb2", 0.85), ("kb3", 0.80)]

    items = {
        "kb1": _make_kb_item("kb1", "Item 1"),
        "kb2": _make_kb_item("kb2", "Item 2"),
        "kb3": _make_kb_item("kb3", "Item 3"),
    }
    mock_kb_repo.get_by_id.side_effect = lambda kb_id: items.get(kb_id)

    response = Mock()
    response.output_text = "Ancliar."
    mock_client.responses.create.return_value = response

    chat = ChatService(
        embedding_service=mock_embedding_service,
        qdrant_service=mock_qdrant_service,
        api_key="test-key",
    )

    result = chat.ancliar(
        question="Question",
        kb_repo=mock_kb_repo,
        client_scope="standard",
        client_code=None,
    )

    # Verify all sources returned for traceability
    assert len(result.sources) == 3
    source_ids = [s.kb_id for s in result.sources]
    assert source_ids == ["kb1", "kb2", "kb3"]


def test_build_context_pack():
    """Test context pack building."""
    items = [
        (_make_kb_item("kb1", "First Item"), 0.95),
        (_make_kb_item("kb2", "Second Item"), 0.90),
    ]

    context = ChatService._build_context_pack(items)

    assert "First Item" in context
    assert "Second Item" in context
    assert "0.950" in context
    assert "kb1" in context
    assert "RUNBOOK" in context


def test_build_context_pack_empty():
    """Test empty context pack."""
    context = ChatService._build_context_pack([])
    assert "No relevant knowledge items found" in context


# --- EmbeddingService tests ---

@patch("src.assistant.retrieval.embedding_service.OpenAI")
def test_embedding_service_embed(mock_openai_class):
    """Test embedding generation."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_response = Mock()
    mock_data = Mock()
    mock_data.embedding = [0.1] * 3072
    mock_response.data = [mock_data]
    mock_client.embeddings.create.return_value = mock_response

    service = EmbeddingService(api_key="test-key")
    result = service.embed("Test text")

    assert len(result) == 3072
    mock_client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-large",
        input="Test text",
    )


@patch("src.assistant.retrieval.embedding_service.OpenAI")
def test_embedding_service_embed_batch(mock_openai_class):
    """Test batch embedding generation."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_data1 = Mock()
    mock_data1.embedding = [0.1] * 3072
    mock_data2 = Mock()
    mock_data2.embedding = [0.2] * 3072
    mock_response = Mock()
    mock_response.data = [mock_data1, mock_data2]
    mock_client.embeddings.create.return_value = mock_response

    service = EmbeddingService(api_key="test-key")
    results = service.embed_batch(["Text 1", "Text 2"])

    assert len(results) == 2
    assert len(results[0]) == 3072
