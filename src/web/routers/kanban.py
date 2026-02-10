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
