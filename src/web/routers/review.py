"""Review router for KB item approval/rejection."""
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.web.dependencies import get_state, get_openai_api_key, get_client_manager, get_template_context, templates

log = logging.getLogger(__name__)
router = APIRouter()


def _get_kb_repo(state, scope):
    from src.assistant.storage.kb_repository import KBItemRepository
    cm = get_client_manager()
    if scope == "standard":
        db_path = cm.get_standard_dir() / "assistant_kb.sqlite"
    else:
        code = state.active_client_code
        if not code:
            return None
        db_path = cm.get_client_dir(code) / "assistant_kb.sqlite"
    return KBItemRepository(db_path)


def _item_to_dict(item):
    return {
        "kb_id": item.kb_id,
        "type": item.type,
        "title": item.title,
        "content_markdown": item.content_markdown,
        "tags": json.loads(item.tags_json) if item.tags_json else [],
        "sap_objects": json.loads(item.sap_objects_json) if item.sap_objects_json else [],
        "signals": json.loads(item.signals_json) if item.signals_json else {},
        "version": item.version,
        "status": item.status,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.get("/review")
async def review_page(request: Request):
    ctx = get_template_context(request)
    return templates.TemplateResponse("review.html", ctx)


@router.get("/api/review/items")
async def list_items(request: Request, scope: str = "standard", status: str | None = None):
    from src.assistant.storage.models import KBItemStatus

    state = get_state(request)
    repo = _get_kb_repo(state, scope)
    if not repo:
        return []

    client_code = state.active_client_code if scope == "client" else None
    status_filter = KBItemStatus(status) if status and status != "ALL" else None
    items = repo.list_by_scope(scope, client_code=client_code, status=status_filter)
    return [_item_to_dict(i) for i in items]


@router.get("/api/review/items/{kb_id}")
async def get_item(kb_id: str, request: Request, scope: str = "standard"):
    state = get_state(request)
    repo = _get_kb_repo(state, scope)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)
    item = repo.get_by_id(kb_id)
    if not item:
        return JSONResponse({"error": "Item not found."}, status_code=404)
    return _item_to_dict(item)


@router.post("/api/review/items/{kb_id}/approve")
async def approve_item(kb_id: str, request: Request):
    from src.assistant.storage.models import KBItemStatus
    from src.shared.errors import format_openai_error, format_qdrant_error

    body = await request.json()
    scope = body.get("scope", "standard")
    state = get_state(request)
    repo = _get_kb_repo(state, scope)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    # Persist edits before approve
    repo.update_fields(
        kb_id,
        title=body.get("title"),
        content_markdown=body.get("content_markdown"),
        tags=body.get("tags"),
        sap_objects=body.get("sap_objects"),
    )
    repo.update_status(kb_id, KBItemStatus.APPROVED)
    updated = repo.get_by_id(kb_id)

    # Embed and index in Qdrant
    indexing_error = None
    try:
        api_key = get_openai_api_key(request)
        from src.assistant.retrieval.embedding_service import EmbeddingService
        from src.assistant.retrieval.qdrant_service import QdrantService

        embed_svc = EmbeddingService(api_key=api_key)
        embedding = embed_svc.embed(f"{updated.title}\n\n{updated.content_markdown}")
        qdrant_svc = QdrantService(state.qdrant_url)
        qdrant_svc.upsert_kb_item(updated, embedding)
    except Exception as e:
        log.exception("Approve indexing error")
        try:
            if "qdrant" in type(e).__module__.lower():
                indexing_error = format_qdrant_error(e)
            else:
                indexing_error = format_openai_error(e)
        except Exception:
            indexing_error = str(e)

    result = _item_to_dict(updated)
    if indexing_error:
        result["indexing_warning"] = indexing_error
    return result


@router.post("/api/review/items/{kb_id}/reject")
async def reject_item(kb_id: str, request: Request):
    from src.assistant.storage.models import KBItemStatus

    body = await request.json()
    scope = body.get("scope", "standard")
    state = get_state(request)
    repo = _get_kb_repo(state, scope)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    repo.update_status(kb_id, KBItemStatus.REJECTED)
    item = repo.get_by_id(kb_id)
    return _item_to_dict(item)
