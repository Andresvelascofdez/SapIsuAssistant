"""
Qdrant service for vector storage and retrieval per PLAN.md section 4.
"""
import json
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams,
)

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
        self.client = QdrantClient(url=qdrant_url)

    def _get_collection_name(self, client_scope: str, client_code: Optional[str]) -> str:
        if client_scope == "standard":
            return "kb_standard"
        elif client_scope == "client":
            if not client_code:
                raise ValueError("client_code required for client scope")
            return f"kb_{client_code.upper()}"
        else:
            raise ValueError(f"Invalid client_scope: {client_scope}")

    def ensure_collection_exists(self, client_scope: str, client_code: Optional[str]):
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
        if kb_item.status != "APPROVED":
            raise ValueError(f"Only APPROVED items can be indexed, got status: {kb_item.status}")

        if len(embedding) != self.VECTOR_SIZE:
            raise ValueError(f"Embedding must be {self.VECTOR_SIZE} dimensions, got {len(embedding)}")

        collection_name = self._get_collection_name(kb_item.client_scope, kb_item.client_code)
        self.ensure_collection_exists(kb_item.client_scope, kb_item.client_code)

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
        scope: str,
        client_code: Optional[str] = None,
        limit: int = 8,
        type_filter: Optional[str] = None,
    ) -> list[tuple[str, float]]:
        """
        Search for KB items using explicit scope.

        Args:
            query_embedding: Query vector (3072 dimensions)
            scope: "general" | "client" | "client_plus_standard"
            client_code: Active client code (required if scope involves client)
            limit: Number of results (default 8)
            type_filter: Optional KB item type filter (e.g. "INCIDENT_PATTERN")

        Returns:
            List of (kb_id, score) tuples
        """
        if len(query_embedding) != self.VECTOR_SIZE:
            raise ValueError(f"Embedding must be {self.VECTOR_SIZE} dimensions")

        # Build optional Qdrant filter for type
        query_filter = None
        if type_filter:
            query_filter = Filter(
                must=[FieldCondition(key="type", match=MatchValue(value=type_filter))]
            )

        results = []

        # Determine which collections to query based on scope
        query_standard = scope in ("general", "client_plus_standard")
        query_client = scope in ("client", "client_plus_standard")

        if query_standard:
            if self.client.collection_exists("kb_standard"):
                hits = self.client.search(
                    collection_name="kb_standard",
                    query_vector=query_embedding,
                    query_filter=query_filter,
                    limit=limit,
                )
                results.extend([
                    (hit.payload["kb_id"], hit.score)
                    for hit in hits
                ])

        if query_client and client_code:
            client_collection = f"kb_{client_code.upper()}"
            if self.client.collection_exists(client_collection):
                hits = self.client.search(
                    collection_name=client_collection,
                    query_vector=query_embedding,
                    query_filter=query_filter,
                    limit=limit,
                )
                results.extend([
                    (hit.payload["kb_id"], hit.score)
                    for hit in hits
                ])

        # Sort by score descending and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def delete_kb_item(self, kb_item: KBItem):
        collection_name = self._get_collection_name(kb_item.client_scope, kb_item.client_code)

        if self.client.collection_exists(collection_name):
            self.client.delete(
                collection_name=collection_name,
                points_selector=[kb_item.kb_id],
            )
