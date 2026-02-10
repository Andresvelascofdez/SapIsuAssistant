"""Chat router with SSE streaming."""
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from src.web.dependencies import (
    get_state, get_openai_api_key, get_client_manager, get_template_context, templates,
)

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/chat")
async def chat_page(request: Request):
    ctx = get_template_context(request)
    return templates.TemplateResponse("chat.html", ctx)


@router.post("/api/chat/send")
async def chat_send(request: Request):
    body = await request.json()
    question = body.get("question", "").strip()
    reasoning_effort = body.get("reasoning_effort", "high")

    if not question:
        return JSONResponse({"error": "Question is empty."}, status_code=400)

    state = get_state(request)
    api_key = get_openai_api_key(request)

    async def event_generator():
        try:
            yield {"event": "thinking", "data": json.dumps({"message": "Processing..."})}

            from src.assistant.retrieval.embedding_service import EmbeddingService
            from src.assistant.retrieval.qdrant_service import QdrantService
            from src.assistant.chat.chat_service import ChatService, ChatError
            from src.assistant.storage.kb_repository import KBItemRepository

            embed_svc = EmbeddingService(api_key=api_key)
            qdrant_svc = QdrantService(state.qdrant_url)
            chat_svc = ChatService(embed_svc, qdrant_svc, api_key=api_key)

            cm = get_client_manager()
            scope = "client" if state.active_client_code else "standard"
            client_code = state.active_client_code

            if scope == "client" and client_code:
                db_path = cm.get_client_dir(client_code) / "assistant_kb.sqlite"
            else:
                db_path = cm.get_standard_dir() / "assistant_kb.sqlite"

            kb_repo = KBItemRepository(db_path)

            result = chat_svc.answer(
                question=question,
                kb_repo=kb_repo,
                client_scope=scope,
                client_code=client_code,
                include_standard=state.standard_kb_enabled,
                reasoning_effort=reasoning_effort,
            )

            sources = []
            for s in result.sources:
                sources.append({
                    "kb_id": s.kb_id,
                    "title": s.title,
                    "type": s.type,
                    "tags": json.loads(s.tags_json) if s.tags_json else [],
                })

            yield {
                "event": "answer",
                "data": json.dumps({
                    "answer": result.answer,
                    "sources": sources,
                }),
            }

        except Exception as e:
            log.exception("Chat error")
            from src.assistant.chat.chat_service import ChatError
            msg = str(e) if isinstance(e, ChatError) else f"Error: {e}"
            yield {"event": "error", "data": json.dumps({"message": msg})}

    return EventSourceResponse(event_generator())
