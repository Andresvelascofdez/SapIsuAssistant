"""
Assistant chat service with RAG per PLAN.md section 10.
"""
import json
import re
from typing import Optional

from openai import OpenAI

from src.assistant.retrieval.embedding_service import EmbeddingService
from src.assistant.retrieval.qdrant_service import QdrantService
from src.assistant.storage.kb_repository import KBItemRepository
from src.assistant.storage.models import KBItem
from src.shared.errors import format_openai_error, format_qdrant_error
from src.shared.tokens import count_tokens, truncate_to_token_limit

ASSISTANT_SYSTEM_PROMPT = """You are an SAP IS-U technical assistant. Answer questions using ONLY the provided context.

Hard constraints:
- Do not reference Kanban or operational tickets.
- Do not assume facts not supported by the context provided.
- If the context is insufficient, list what information is missing under "Missing inputs".
- Be precise and technical. Reference SAP transactions, programs, and objects where relevant.
- Structure your answers clearly with headings and steps where appropriate."""

# Reserve tokens for system prompt + question + response
MAX_CONTEXT_TOKENS = 100_000

# Deterministic boost values for tag/sap_object matching
TAG_BOOST = 0.05
SAP_OBJECT_BOOST = 0.05


class ChatService:
    """
    Assistant chat with RAG.

    Flow:
    1. Embed the user question (text-embedding-3-large)
    2. Query Qdrant by scope (general / client / client_plus_standard)
    3. Fetch KB items from SQLite by kb_id, validate APPROVED status
    4. Apply deterministic ranking boost for tag/sap_object matches
    5. If no valid items found -> return immediately (skip GPT, save tokens)
    6. Build context pack (with token budget)
    7. Call OpenAI for answer (gpt-5.2, reasoning effort high/xhigh)
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
        scope: str = "general",
        client_code: Optional[str] = None,
        top_k: int = 8,
        reasoning_effort: str = "high",
        type_filter: Optional[str] = None,
    ) -> "ChatResult":
        """
        Answer a question using RAG with scope-aware retrieval and token gating.

        Args:
            question: User question
            kb_repo: KB item repository for SQLite lookups
            scope: "general" | "client" | "client_plus_standard"
            client_code: Active client code (required for client/client_plus_standard scopes)
            top_k: Max results to retrieve
            reasoning_effort: "high" or "xhigh"
            type_filter: Optional KB item type filter

        Returns:
            ChatResult with answer, sources, model_called flag, and used_kb_items

        Raises:
            ChatError: With actionable error message
        """
        try:
            query_embedding = self.embedding_service.embed(question)
        except Exception as e:
            raise ChatError(format_openai_error(e)) from e

        try:
            search_results = self.qdrant_service.search(
                query_embedding=query_embedding,
                scope=scope,
                client_code=client_code,
                limit=top_k,
                type_filter=type_filter,
            )
        except Exception as e:
            raise ChatError(format_qdrant_error(e)) from e

        # Fetch from SQLite, validate APPROVED status, apply ranking boost
        source_items = self._fetch_and_boost(search_results, kb_repo, question)

        # Token gating: skip GPT if no valid results
        if not source_items:
            return ChatResult(
                answer=(
                    "No se encontraron resultados relevantes en el alcance "
                    "seleccionado. No se ha realizado consulta al modelo para "
                    "ahorrar tokens.\n\n"
                    "**Sugerencias:**\n"
                    "- Ingesta documentación relevante desde la pestaña **Ingesta** "
                    "y apruébala en **Review**.\n"
                    "- Verifica que el alcance seleccionado (General / Cliente / "
                    "Cliente + Standard) contiene información relevante.\n"
                    "- Si usaste filtro de tipo, prueba sin filtro."
                ),
                sources=[],
                model_called=False,
                used_kb_items=[],
            )

        context_pack = self._build_context_pack(source_items, MAX_CONTEXT_TOKENS)

        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=ASSISTANT_SYSTEM_PROMPT,
                input=f"## Question\n\n{question}\n\n## Context\n\n{context_pack}",
                reasoning={"effort": reasoning_effort},
            )
        except Exception as e:
            raise ChatError(format_openai_error(e)) from e

        sources = [item for item, _ in source_items]
        used_kb_items = [
            {"kb_id": item.kb_id, "title": item.title, "type": item.type}
            for item in sources
        ]

        return ChatResult(
            answer=response.output_text,
            sources=sources,
            model_called=True,
            used_kb_items=used_kb_items,
        )

    def _fetch_and_boost(
        self,
        search_results: list[tuple[str, float]],
        kb_repo: KBItemRepository,
        question: str,
    ) -> list[tuple[KBItem, float]]:
        """
        Fetch KB items from SQLite, validate APPROVED status, and apply
        deterministic ranking boost based on tag/sap_object matches.
        """
        # Tokenize query for boost matching
        query_tokens = set(re.findall(r'[A-Za-z0-9_/]+', question.upper()))

        source_items = []
        for kb_id, score in search_results:
            item = kb_repo.get_by_id(kb_id)
            # Only include items that exist in SQLite AND are APPROVED
            if not item or item.status != "APPROVED":
                continue

            # Deterministic ranking boost
            boost = 0.0
            try:
                tags = set(t.upper() for t in json.loads(item.tags_json))
                sap_objects = set(o.upper() for o in json.loads(item.sap_objects_json))
            except (json.JSONDecodeError, TypeError):
                tags = set()
                sap_objects = set()

            for token in query_tokens:
                if token in tags:
                    boost += TAG_BOOST
                if token in sap_objects:
                    boost += SAP_OBJECT_BOOST

            source_items.append((item, score + boost))

        # Re-sort by boosted score
        source_items.sort(key=lambda x: x[1], reverse=True)
        return source_items

    @staticmethod
    def _build_context_pack(
        source_items: list[tuple[KBItem, float]],
        max_tokens: int = MAX_CONTEXT_TOKENS,
    ) -> str:
        """Build context pack from retrieved KB items with token budget."""
        if not source_items:
            return "No relevant knowledge items found."

        sections = []
        total_tokens = 0

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

            section_tokens = count_tokens(section)
            if total_tokens + section_tokens > max_tokens:
                remaining = max_tokens - total_tokens
                if remaining > 100:
                    section = truncate_to_token_limit(section, remaining)
                    sections.append(section)
                break

            sections.append(section)
            total_tokens += section_tokens

        return "\n\n---\n\n".join(sections)


class ChatError(Exception):
    """Chat error with actionable user message."""
    pass


class ChatResult:
    """Result of a chat interaction with traceability."""

    def __init__(
        self,
        answer: str,
        sources: list[KBItem],
        model_called: bool = False,
        used_kb_items: list[dict] | None = None,
    ):
        self.answer = answer
        self.sources = sources
        self.model_called = model_called
        self.used_kb_items = used_kb_items or []
