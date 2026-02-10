"""
Assistant chat service with RAG per PLAN.md section 10.
"""
import json
from typing import Optional

from openai import OpenAI

from src.assistant.retrieval.embedding_service import EmbeddingService
from src.assistant.retrieval.qdrant_service import QdrantService
from src.assistant.storage.kb_repository import KBItemRepository
from src.assistant.storage.models import KBItem


ASSISTANT_SYSTEM_PROMPT = """You are an SAP IS-U technical assistant. Answer questions using ONLY the provided context.

Hard constraints:
- Do not reference Kanban or operational tickets.
- Do not assume facts not supported by the context provided.
- If the context is insufficient, list what information is missing under "Missing inputs".
- Be precise and technical. Reference SAP transactions, programs, and objects where relevant.
- Structure your answers clearly with headings and steps where appropriate."""


class ChatService:
    """
    Assistant chat with RAG per PLAN.md section 10.

    Flow:
    1. Embed the user question (text-embedding-3-large)
    2. Query Qdrant (kb_standard if enabled + kb_<ACTIVE_CLIENT>)
    3. Fetch KB items from SQLite by kb_id
    4. Build context pack
    5. Call OpenAI for answer (gpt-5.2, reasoning effort high/xhigh)
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        qdrant_service: QdrantService,
        model: str = "gpt-5.2",
        api_key: str | None = None,
    ):
        self.embedding_service = embedding_service
        self.qdrant_service = qdrant_service
        self.client = OpenAI(api_key=api_key) if api_key else OpenAI()
        self.model = model

    def answer(
        self,
        question: str,
        kb_repo: KBItemRepository,
        client_scope: str,
        client_code: Optional[str],
        include_standard: bool = True,
        top_k: int = 8,
        reasoning_effort: str = "high",
    ) -> "ChatResult":
        """
        Answer a question using RAG per PLAN.md section 10.

        Args:
            question: User question
            kb_repo: KB repository to fetch full items
            client_scope: "standard" or "client"
            client_code: Active client code
            include_standard: Whether to include standard KB
            top_k: Number of results (default 8 per PLAN.md)
            reasoning_effort: "high" (default) or "xhigh" per PLAN.md section 10.2

        Returns:
            ChatResult with answer and source KB items
        """
        # Step 1: Embed question
        query_embedding = self.embedding_service.embed(question)

        # Step 2: Query Qdrant
        search_results = self.qdrant_service.search(
            query_embedding=query_embedding,
            client_scope=client_scope,
            client_code=client_code,
            limit=top_k,
            include_standard=include_standard,
        )

        # Step 3: Fetch KB items from SQLite
        source_items = []
        for kb_id, score in search_results:
            item = kb_repo.get_by_id(kb_id)
            if item:
                source_items.append((item, score))

        # Step 4: Build context pack
        context_pack = self._build_context_pack(source_items)

        # Step 5: Call OpenAI
        response = self.client.responses.create(
            model=self.model,
            instructions=ASSISTANT_SYSTEM_PROMPT,
            input=f"## Question\n\n{question}\n\n## Context\n\n{context_pack}",
            reasoning={"effort": reasoning_effort},
        )

        return ChatResult(
            answer=response.output_text,
            sources=[item for item, _ in source_items],
        )

    @staticmethod
    def _build_context_pack(source_items: list[tuple[KBItem, float]]) -> str:
        """Build context pack from retrieved KB items per PLAN.md section 10.2."""
        if not source_items:
            return "No relevant knowledge items found."

        sections = []
        for i, (item, score) in enumerate(source_items, 1):
            tags = json.loads(item.tags_json)
            sap_objects = json.loads(item.sap_objects_json)

            section = (
                f"### [{i}] {item.title}\n"
                f"Type: {item.type} | Tags: {', '.join(tags)} | "
                f"SAP Objects: {', '.join(sap_objects)}\n"
                f"Score: {score:.3f} | ID: {item.kb_id}\n\n"
                f"{item.content_markdown}"
            )
            sections.append(section)

        return "\n\n---\n\n".join(sections)


class ChatResult:
    """Result of a chat interaction with traceability."""

    def __init__(self, answer: str, sources: list[KBItem]):
        self.answer = answer
        self.sources = sources
