"""Shared KB approval/indexing helpers."""

from src.assistant.storage.models import KBItem


def index_approved_kb_item(
    kb_item: KBItem,
    *,
    api_key: str | None = None,
    qdrant_url: str = "http://localhost:6333",
) -> None:
    """Embed and upsert an already-approved KB item into Qdrant."""
    from src.assistant.retrieval.embedding_service import EmbeddingService
    from src.assistant.retrieval.qdrant_service import QdrantService

    embed_svc = EmbeddingService(api_key=api_key)
    embedding = embed_svc.embed(f"{kb_item.title}\n\n{kb_item.content_markdown}")
    qdrant_svc = QdrantService(qdrant_url)
    qdrant_svc.upsert_kb_item(kb_item, embedding)
