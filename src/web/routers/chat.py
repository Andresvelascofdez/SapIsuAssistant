"""Chat router with SSE streaming and session management."""
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sse_starlette.sse import EventSourceResponse

from src.web.dependencies import (
    get_state, get_openai_api_key, get_client_manager, get_chat_repository,
    get_template_context, templates,
)

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/chat")
async def chat_page(request: Request):
    ctx = get_template_context(request)
    return templates.TemplateResponse("chat.html", ctx)


# ── Chat send (with session persistence) ──


@router.post("/api/chat/send")
async def chat_send(request: Request):
    body = await request.json()
    question = body.get("question", "").strip()
    reasoning_effort = body.get("reasoning_effort", "high")
    scope = body.get("scope", "general")
    type_filter = body.get("type_filter") or None
    session_id = body.get("session_id")

    if not question:
        return JSONResponse({"error": "Question is empty."}, status_code=400)

    if scope not in ("general", "client", "client_plus_standard"):
        return JSONResponse({"error": "Invalid scope."}, status_code=400)

    state = get_state(request)
    api_key = get_openai_api_key(request)

    async def event_generator():
        try:
            yield {"event": "thinking", "data": json.dumps({"message": "Processing..."})}

            from src.assistant.retrieval.embedding_service import EmbeddingService
            from src.assistant.retrieval.qdrant_service import QdrantService
            from src.assistant.chat.chat_service import ChatService, ChatError

            embed_svc = EmbeddingService(api_key=api_key)
            qdrant_svc = QdrantService(state.qdrant_url)
            chat_svc = ChatService(embed_svc, qdrant_svc, api_key=api_key)

            cm = get_client_manager()
            client_code = state.active_client_code

            # Determine KB repo path based on scope
            if scope in ("client", "client_plus_standard") and client_code:
                from src.assistant.storage.kb_repository import KBItemRepository
                db_path = cm.get_client_dir(client_code) / "assistant_kb.sqlite"
                kb_repo = KBItemRepository(db_path)
            else:
                from src.assistant.storage.kb_repository import KBItemRepository
                db_path = cm.get_standard_dir() / "assistant_kb.sqlite"
                kb_repo = KBItemRepository(db_path)

            result = chat_svc.answer(
                question=question,
                kb_repo=kb_repo,
                scope=scope,
                client_code=client_code,
                reasoning_effort=reasoning_effort,
                type_filter=type_filter,
            )

            # Persist messages if session_id provided
            current_session_id = session_id
            if current_session_id:
                try:
                    chat_repo = get_chat_repository()
                    # Save user message
                    chat_repo.add_message(
                        session_id=current_session_id,
                        role="user",
                        content=question,
                    )
                    # Save assistant response
                    chat_repo.add_message(
                        session_id=current_session_id,
                        role="assistant",
                        content=result.answer,
                        used_kb_items_json=json.dumps(result.used_kb_items),
                        model_called=1 if result.model_called else 0,
                    )
                except Exception as pe:
                    log.warning("Failed to persist chat message: %s", pe)

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
                    "model_called": result.model_called,
                    "used_kb_items": result.used_kb_items,
                }),
            }

        except Exception as e:
            log.exception("Chat error")
            from src.assistant.chat.chat_service import ChatError
            msg = str(e) if isinstance(e, ChatError) else f"Error: {e}"
            yield {"event": "error", "data": json.dumps({"message": msg})}

    return EventSourceResponse(event_generator())


# ── Session management ──


@router.get("/api/chat/sessions")
async def list_sessions(request: Request):
    search = request.query_params.get("search", "").strip()
    chat_repo = get_chat_repository()
    if search:
        sessions = chat_repo.search_sessions(search)
    else:
        sessions = chat_repo.list_sessions()
    return [
        {
            "session_id": s.session_id,
            "scope": s.scope,
            "client_code": s.client_code,
            "title": s.title,
            "is_pinned": s.is_pinned,
            "created_at": s.created_at,
            "last_message_at": s.last_message_at,
        }
        for s in sessions
    ]


@router.post("/api/chat/sessions")
async def create_session(request: Request):
    body = await request.json()
    scope = body.get("scope", "general")
    client_code = body.get("client_code")
    title = body.get("title", "New Chat")

    chat_repo = get_chat_repository()
    session = chat_repo.create_session(scope=scope, client_code=client_code, title=title)
    return {
        "session_id": session.session_id,
        "scope": session.scope,
        "client_code": session.client_code,
        "title": session.title,
        "is_pinned": session.is_pinned,
        "created_at": session.created_at,
        "last_message_at": session.last_message_at,
    }


@router.get("/api/chat/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    chat_repo = get_chat_repository()
    session = chat_repo.get_session(session_id)
    if not session:
        return JSONResponse({"error": "Session not found."}, status_code=404)
    messages = chat_repo.get_messages(session_id)
    return [
        {
            "message_id": m.message_id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at,
            "used_kb_items": json.loads(m.used_kb_items_json),
            "model_called": m.model_called,
        }
        for m in messages
    ]


@router.put("/api/chat/sessions/{session_id}/rename")
async def rename_session(session_id: str, request: Request):
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return JSONResponse({"error": "Title is required."}, status_code=400)

    chat_repo = get_chat_repository()
    session = chat_repo.rename_session(session_id, title)
    if not session:
        return JSONResponse({"error": "Session not found."}, status_code=404)
    return {"session_id": session.session_id, "title": session.title}


@router.put("/api/chat/sessions/{session_id}/pin")
async def pin_session(session_id: str, request: Request):
    body = await request.json()
    pinned = body.get("pinned", True)

    chat_repo = get_chat_repository()
    session = chat_repo.pin_session(session_id, pinned)
    if not session:
        return JSONResponse({"error": "Session not found."}, status_code=404)
    return {"session_id": session.session_id, "is_pinned": session.is_pinned}


@router.delete("/api/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    chat_repo = get_chat_repository()
    if chat_repo.delete_session(session_id):
        return {"status": "deleted"}
    return JSONResponse({"error": "Session not found."}, status_code=404)


@router.get("/api/chat/sessions/{session_id}/export")
async def export_session(session_id: str, request: Request):
    fmt = request.query_params.get("format", "json")
    chat_repo = get_chat_repository()

    if fmt == "md":
        content = chat_repo.export_session_markdown(session_id)
        if content is None:
            return JSONResponse({"error": "Session not found."}, status_code=404)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=chat_{session_id[:8]}.md"},
        )
    else:
        content = chat_repo.export_session_json(session_id)
        if content is None:
            return JSONResponse({"error": "Session not found."}, status_code=404)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=chat_{session_id[:8]}.json"},
        )


# ── Retention settings ──


@router.post("/api/chat/retention")
async def set_retention(request: Request):
    body = await request.json()
    days = body.get("days", 30)
    if days not in (7, 15, 30):
        return JSONResponse({"error": "Retention must be 7, 15, or 30 days."}, status_code=400)
    request.session["chat_retention_days"] = days
    # Run cleanup immediately
    chat_repo = get_chat_repository()
    deleted = chat_repo.cleanup_retention(days)
    return {"chat_retention_days": days, "sessions_deleted": deleted}
