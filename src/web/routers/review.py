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


def _format_indexing_error(error: Exception) -> str:
    from src.shared.errors import format_openai_error, format_qdrant_error

    try:
        if "qdrant" in type(error).__module__.lower():
            return format_qdrant_error(error)
        return format_openai_error(error)
    except Exception:
        return str(error)


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
        from src.assistant.retrieval.kb_indexer import index_approved_kb_item

        index_approved_kb_item(updated, api_key=api_key, qdrant_url=state.qdrant_url)
    except Exception as e:
        log.exception("Approve indexing error")
        indexing_error = _format_indexing_error(e)

    result = _item_to_dict(updated)
    if indexing_error:
        result["indexing_warning"] = indexing_error
    return result


@router.post("/api/review/items/bulk-approve")
async def bulk_approve_items(request: Request):
    from src.assistant.storage.models import KBItemStatus
    from src.assistant.retrieval.kb_indexer import index_approved_kb_item

    body = await request.json()
    scope = body.get("scope", "standard")
    state = get_state(request)
    repo = _get_kb_repo(state, scope)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    client_code = state.active_client_code if scope == "client" else None
    drafts = repo.list_by_scope(scope, client_code=client_code, status=KBItemStatus.DRAFT)
    api_key = get_openai_api_key(request)

    approved = []
    errors = []
    for draft in drafts:
        updated = repo.update_status(draft.kb_id, KBItemStatus.APPROVED)
        try:
            index_approved_kb_item(updated, api_key=api_key, qdrant_url=state.qdrant_url)
            approved.append(_item_to_dict(updated))
        except Exception as e:
            log.exception("Bulk approve indexing error for %s", draft.kb_id)
            repo.update_status(draft.kb_id, KBItemStatus.DRAFT)
            errors.append({
                "kb_id": draft.kb_id,
                "title": draft.title,
                "error": _format_indexing_error(e),
            })

    return {
        "scope": scope,
        "client_code": client_code,
        "requested_count": len(drafts),
        "approved_count": len(approved),
        "indexed_count": len(approved),
        "failed_count": len(errors),
        "items": approved,
        "errors": errors,
    }


@router.post("/api/review/items/{kb_id}/reject")
async def reject_item(kb_id: str, request: Request):
    from src.assistant.storage.models import KBItemStatus

    body = await request.json()
    scope = body.get("scope", "standard")
    state = get_state(request)
    repo = _get_kb_repo(state, scope)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    existing = repo.get_by_id(kb_id)
    deletion_warning = None
    if existing and existing.status == KBItemStatus.APPROVED.value:
        try:
            from src.assistant.retrieval.qdrant_service import QdrantService

            QdrantService(state.qdrant_url).delete_kb_item(existing)
        except Exception as e:
            log.exception("Reject vector deletion error")
            deletion_warning = _format_indexing_error(e)

    repo.update_status(kb_id, KBItemStatus.REJECTED)
    item = repo.get_by_id(kb_id)
    result = _item_to_dict(item)
    if deletion_warning:
        result["deletion_warning"] = deletion_warning
    return result
