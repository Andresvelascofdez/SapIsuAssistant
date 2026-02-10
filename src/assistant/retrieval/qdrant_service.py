"""
Qdrant service for vector storage and retrieval per PLAN.md section 4.
"""
import json
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.assistant.storage.kb_repository import KBItemRepository
from src.assistant.storage.models import KBItem

log = logging.getLogger(__name__)


class QdrantService:
    """
    Qdrant integration for KB item indexing and retrieval.

    Collections per PLAN.md section 4.1:
    - kb_standard
    - kb_<CLIENT_CODE> (e.g., kb_SWE, kb_HERON)

    Vector config per PLAN.md section 4.2:
    - Vector size: 3072 (text-embedding-3-large)
    - Distance: cosine

    Payload per PLAN.md section 4.4:
    - kb_id, type, title, tags, sap_objects, client_scope, client_code, version, updated_at
    """

    VECTOR_SIZE = 3072
    DISTANCE = Distance.COSINE

    def __init__(self, qdrant_url: str = "http://localhost:6333"):
        """
        Initialize Qdrant service.

        Args:
            qdrant_url: Qdrant server URL
        """
        self.client = QdrantClient(url=qdrant_url)

    def _get_collection_name(self, client_scope: str, client_code: Optional[str]) -> str:
        """
        Get collection name per PLAN.md section 4.1.

        Args:
            client_scope: "standard" or "client"
            client_code: Client code (required if scope="client")

        Returns:
            Collection name
        """
        if client_scope == "standard":
            return "kb_standard"
        elif client_scope == "client":
            if not client_code:
                raise ValueError("client_code required for client scope")
            return f"kb_{client_code.upper()}"
        else:
            raise ValueError(f"Invalid client_scope: {client_scope}")

    def ensure_collection_exists(self, client_scope: str, client_code: Optional[str]):
        """
        Create collection if it doesn't exist per PLAN.md section 4.1.
        Validates vector dimensions match on existing collections.
        """
        collection_name = self._get_collection_name(client_scope, client_code)

        if self.client.collection_exists(collection_name):
            info = self.client.get_collection(collection_name)
            existing_size = getattr(info.config.params.vectors, "size", None)
            if existing_size and existing_size != self.VECTOR_SIZE:
                log.error(
                    "Collection %s has vector size %d, expected %d. "
                    "Delete and recreate the collection.",
                    collection_name, existing_size, self.VECTOR_SIZE,
                )
                raise ValueError(
                    f"Collection '{collection_name}' vector size mismatch: "
                    f"has {existing_size}, expected {self.VECTOR_SIZE}. "
                    f"Delete and recreate the collection."
                )
        else:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=self.DISTANCE,
                ),
            )

    def upsert_kb_item(self, kb_item: KBItem, embedding: list[float]):
        """
        Upsert KB item into Qdrant per PLAN.md section 4.5.

        Only APPROVED items should be indexed per PLAN.md section 4.5.

        Args:
            kb_item: KB item to index
            embedding: Vector embedding (3072 dimensions)

        Raises:
            ValueError: If item is not APPROVED
        """
        if kb_item.status != "APPROVED":
            raise ValueError(f"Only APPROVED items can be indexed, got status: {kb_item.status}")

        if len(embedding) != self.VECTOR_SIZE:
            raise ValueError(f"Embedding must be {self.VECTOR_SIZE} dimensions, got {len(embedding)}")

        collection_name = self._get_collection_name(kb_item.client_scope, kb_item.client_code)

        # Ensure collection exists
        self.ensure_collection_exists(kb_item.client_scope, kb_item.client_code)

        # Build payload per PLAN.md section 4.4
        payload = {
            "kb_id": kb_item.kb_id,
            "type": kb_item.type,
            "title": kb_item.title,
            "tags": json.loads(kb_item.tags_json),
            "sap_objects": json.loads(kb_item.sap_objects_json),
            "client_scope": kb_item.client_scope,
            "client_code": kb_item.client_code,
            "version": kb_item.version,
            "updated_at": kb_item.updated_at,
        }

        # Point ID = kb_id per PLAN.md section 4.3
        point = PointStruct(
            id=kb_item.kb_id,
            vector=embedding,
            payload=payload,
        )

        self.client.upsert(
            collection_name=collection_name,
            points=[point],
        )

    def search(
        self,
        query_embedding: list[float],
        client_scope: str,
        client_code: Optional[str],
        limit: int = 8,
        include_standard: bool = True,
    ) -> list[tuple[str, float]]:
        """
        Search for KB items per PLAN.md section 4.6.

        Query rules per PLAN.md section 4.6:
        - Retrieval always queries kb_standard (if enabled) + kb_<ACTIVE_CLIENT>
        - Never query other client collections

        Args:
            query_embedding: Query vector (3072 dimensions)
            client_scope: "standard" or "client"
            client_code: Active client code (required if scope="client")
            limit: Number of results (default 8 per PLAN.md section 10.1)
            include_standard: Whether to include standard KB (default True)

        Returns:
            List of (kb_id, score) tuples
        """
        if len(query_embedding) != self.VECTOR_SIZE:
            raise ValueError(f"Embedding must be {self.VECTOR_SIZE} dimensions")

        results = []

        # Query standard collection if enabled and exists
        if include_standard:
            standard_collection = "kb_standard"
            if self.client.collection_exists(standard_collection):
                standard_results = self.client.search(
                    collection_name=standard_collection,
                    query_vector=query_embedding,
                    limit=limit,
                )
                results.extend([
                    (hit.payload["kb_id"], hit.score)
                    for hit in standard_results
                ])

        # Query client collection if in client scope
        if client_scope == "client" and client_code:
            client_collection = self._get_collection_name(client_scope, client_code)
            if self.client.collection_exists(client_collection):
                client_results = self.client.search(
                    collection_name=client_collection,
                    query_vector=query_embedding,
                    limit=limit,
                )
                results.extend([
                    (hit.payload["kb_id"], hit.score)
                    for hit in client_results
                ])

        # Sort by score descending and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def delete_kb_item(self, kb_item: KBItem):
        """
        Delete KB item from Qdrant.

        Args:
            kb_item: KB item to delete
        """
        collection_name = self._get_collection_name(kb_item.client_scope, kb_item.client_code)

        if self.client.collection_exists(collection_name):
            self.client.delete(
                collection_name=collection_name,
                points_selector=[kb_item.kb_id],
            )
