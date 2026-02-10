"""Kanban router with drag-drop support."""
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.web.dependencies import get_state, get_client_manager, get_template_context, templates

log = logging.getLogger(__name__)
router = APIRouter()


def _get_kanban_repo(state):
    from src.kanban.storage.kanban_repository import KanbanRepository
    code = state.active_client_code
    if not code:
        return None
    db_path = state.data_root / "clients" / code / "kanban.sqlite"
    if not db_path.parent.exists():
        return None
    return KanbanRepository(db_path)


def _get_all_repos(state):
    from src.kanban.storage.kanban_repository import KanbanRepository
    repos = []
    clients_dir = state.data_root / "clients"
    if not clients_dir.exists():
        return repos
    for child in sorted(clients_dir.iterdir()):
        if child.is_dir():
            db_path = child / "kanban.sqlite"
            if db_path.exists():
                repos.append((child.name, KanbanRepository(db_path)))
    return repos


def _ticket_to_dict(t):
    return {
        "id": t.id,
        "ticket_id": t.ticket_id,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "notes": t.notes,
        "tags": json.loads(t.tags_json) if t.tags_json else [],
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "closed_at": t.closed_at,
    }


def _column_to_dict(c):
    return {
        "id": c.id,
        "name": c.name,
        "display_name": c.display_name,
        "position": c.position,
    }


@router.get("/kanban")
async def kanban_page(request: Request):
    ctx = get_template_context(request)
    return templates.TemplateResponse("kanban.html", ctx)


@router.get("/api/kanban/tickets")
async def list_tickets(request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)

    if repo:
        tickets = repo.list_tickets()
    else:
        tickets = []
        for _code, r in _get_all_repos(state):
            tickets.extend(r.list_tickets())

    return [_ticket_to_dict(t) for t in tickets]


@router.post("/api/kanban/tickets")
async def create_ticket(request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return JSONResponse({"error": "Title is required."}, status_code=400)

    ticket = repo.create_ticket(
        title=title,
        priority=body.get("priority", "MEDIUM"),
        notes=body.get("notes") or None,
    )
    return _ticket_to_dict(ticket)


@router.put("/api/kanban/tickets/{ticket_id}/move")
async def move_ticket(ticket_id: str, request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    body = await request.json()
    new_status = body.get("status", "").strip()
    if not new_status:
        return JSONResponse({"error": "Status is required."}, status_code=400)

    ticket = repo.update_status(ticket_id, new_status)
    if not ticket:
        return JSONResponse({"error": "Ticket not found."}, status_code=404)
    return _ticket_to_dict(ticket)


@router.put("/api/kanban/tickets/{ticket_id}")
async def update_ticket(ticket_id: str, request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    body = await request.json()
    ticket = repo.update_ticket(
        ticket_id,
        title=body.get("title"),
        priority=body.get("priority"),
        notes=body.get("notes"),
    )
    if not ticket:
        return JSONResponse({"error": "Ticket not found."}, status_code=404)
    return _ticket_to_dict(ticket)


@router.get("/api/kanban/tickets/{ticket_id}/history")
async def ticket_history(ticket_id: str, request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    history = repo.get_history(ticket_id)
    return [
        {
            "from_status": h.from_status,
            "to_status": h.to_status,
            "changed_at": h.changed_at,
        }
        for h in history
    ]


# ── Column management endpoints ──


@router.get("/api/kanban/columns")
async def list_columns(request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo:
        return []
    return [_column_to_dict(c) for c in repo.list_columns()]


@router.post("/api/kanban/columns")
async def create_column(request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    body = await request.json()
    name = body.get("name", "").strip().upper().replace(" ", "_")
    display_name = body.get("display_name", "").strip()
    if not name or not display_name:
        return JSONResponse({"error": "name and display_name are required."}, status_code=400)

    try:
        col = repo.create_column(name, display_name)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return _column_to_dict(col)


@router.put("/api/kanban/columns/reorder")
async def reorder_columns(request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    body = await request.json()
    ordered_ids = body.get("ordered_ids", [])
    if not ordered_ids:
        return JSONResponse({"error": "ordered_ids is required."}, status_code=400)

    columns = repo.reorder_columns(ordered_ids)
    return [_column_to_dict(c) for c in columns]


@router.put("/api/kanban/columns/{col_id}")
async def rename_column(col_id: int, request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    body = await request.json()
    display_name = body.get("display_name", "").strip()
    if not display_name:
        return JSONResponse({"error": "display_name is required."}, status_code=400)

    col = repo.rename_column(col_id, display_name)
    if not col:
        return JSONResponse({"error": "Column not found."}, status_code=404)
    return _column_to_dict(col)


@router.delete("/api/kanban/columns/{col_id}")
async def delete_column(col_id: int, request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    try:
        deleted = repo.delete_column(col_id)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    if not deleted:
        return JSONResponse({"error": "Column not found."}, status_code=404)
    return {"status": "deleted"}
