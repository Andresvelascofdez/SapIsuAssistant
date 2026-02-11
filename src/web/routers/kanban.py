"""Kanban router with drag-drop support."""
import csv
import io
import json
import logging

from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse

from src.web.dependencies import get_state, get_client_manager, get_template_context, templates

log = logging.getLogger(__name__)
router = APIRouter()


def _get_global_repo(state):
    """Return a KanbanRepository for the global columns database (always available)."""
    from src.kanban.storage.kanban_repository import KanbanRepository
    db_path = state.data_root / "kanban_global.sqlite"
    return KanbanRepository(db_path, seed_columns=True)


def _get_kanban_repo(state):
    """Return a per-client KanbanRepository (tickets only, no column seeding)."""
    from src.kanban.storage.kanban_repository import KanbanRepository
    code = state.active_client_code
    if not code:
        return None
    db_path = state.data_root / "clients" / code / "kanban.sqlite"
    if not db_path.parent.exists():
        return None
    return KanbanRepository(db_path, seed_columns=False)


def _get_kanban_repo_for_client(state, client_code: str):
    """Return a per-client KanbanRepository for an explicit client code."""
    from src.kanban.storage.kanban_repository import KanbanRepository
    if not client_code:
        return None
    db_path = state.data_root / "clients" / client_code / "kanban.sqlite"
    if not db_path.parent.exists():
        return None
    return KanbanRepository(db_path, seed_columns=False)


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
                repos.append((child.name, KanbanRepository(db_path, seed_columns=False)))
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
        "links": json.loads(t.links_json) if t.links_json else [],
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
async def list_tickets(
    request: Request,
    search: str = Query(default=None),
    priority: str = Query(default=None),
    limit: int = Query(default=None),
    offset: int = Query(default=0),
):
    state = get_state(request)
    repo = _get_kanban_repo(state)

    if repo:
        tickets = repo.list_tickets(search=search, priority=priority, limit=limit, offset=offset)
        total = repo.count_tickets(search=search, priority=priority)
    else:
        tickets = []
        total = 0
        for _code, r in _get_all_repos(state):
            tickets.extend(r.list_tickets(search=search, priority=priority))
        total = len(tickets)
        if limit is not None:
            tickets = tickets[offset:offset + limit]

    return {"tickets": [_ticket_to_dict(t) for t in tickets], "total": total}


@router.post("/api/kanban/tickets")
async def create_ticket(request: Request):
    state = get_state(request)
    body = await request.json()

    # Resolve client: explicit from body, or fall back to session
    client_code = body.get("client_code", "").strip()
    if client_code:
        repo = _get_kanban_repo_for_client(state, client_code)
    else:
        repo = _get_kanban_repo(state)

    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    title = body.get("title", "").strip()
    if not title:
        return JSONResponse({"error": "Title is required."}, status_code=400)

    # Get default status from global columns
    global_repo = _get_global_repo(state)
    columns = global_repo.list_columns()
    default_status = columns[0].name if columns else "EN_PROGRESO"

    ticket = repo.create_ticket(
        title=title,
        priority=body.get("priority", "MEDIUM"),
        notes=body.get("notes") or None,
        status=body.get("status") or default_status,
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
        tags=body.get("tags"),
        links=body.get("links"),
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


# ── Column management endpoints (global, no client required) ──


@router.get("/api/kanban/columns")
async def list_columns(request: Request):
    state = get_state(request)
    repo = _get_global_repo(state)
    return [_column_to_dict(c) for c in repo.list_columns()]


@router.post("/api/kanban/columns")
async def create_column(request: Request):
    state = get_state(request)
    repo = _get_global_repo(state)

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
    repo = _get_global_repo(state)

    body = await request.json()
    ordered_ids = body.get("ordered_ids", [])
    if not ordered_ids:
        return JSONResponse({"error": "ordered_ids is required."}, status_code=400)

    columns = repo.reorder_columns(ordered_ids)
    return [_column_to_dict(c) for c in columns]


@router.put("/api/kanban/columns/{col_id}")
async def rename_column(col_id: int, request: Request):
    state = get_state(request)
    repo = _get_global_repo(state)

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
    repo = _get_global_repo(state)

    # Find the column to check for tickets across all clients
    cols = repo.list_columns()
    target_col = next((c for c in cols if c.id == col_id), None)
    if not target_col:
        return JSONResponse({"error": "Column not found."}, status_code=404)

    # Check all client repos for tickets in this column
    total_ticket_count = 0
    for _code, client_repo in _get_all_repos(state):
        total_ticket_count += len(client_repo.list_tickets(status=target_col.name))

    if total_ticket_count > 0:
        return JSONResponse(
            {"error": f"Column '{target_col.display_name}' has {total_ticket_count} ticket(s). Move them first."},
            status_code=400,
        )

    repo.delete_column(col_id)
    return {"status": "deleted"}


# ── CSV import endpoint ──


@router.post("/api/kanban/import-csv")
async def import_csv(request: Request):
    """Import tickets from a CSV file."""
    state = get_state(request)
    body = await request.json()
    csv_path = body.get("csv_path", "").strip()
    if not csv_path:
        return JSONResponse({"error": "csv_path is required."}, status_code=400)

    from pathlib import Path
    from src.kanban.storage.csv_import import import_tickets_from_csv

    csv_file = Path(csv_path)
    if not csv_file.exists():
        return JSONResponse({"error": f"File not found: {csv_path}"}, status_code=400)

    try:
        result = import_tickets_from_csv(csv_file, state.data_root)
    except Exception as e:
        log.exception("CSV import failed")
        return JSONResponse({"error": str(e)}, status_code=500)

    return result


@router.delete("/api/kanban/tickets/{ticket_id}")
async def delete_ticket(ticket_id: str, request: Request):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    deleted = repo.delete_ticket(ticket_id)
    if not deleted:
        return JSONResponse({"error": "Ticket not found."}, status_code=404)
    return {"status": "deleted"}


@router.get("/api/kanban/export-csv")
async def export_csv(request: Request):
    """Export all tickets as a CSV download."""
    state = get_state(request)
    repo = _get_kanban_repo(state)

    if repo:
        tickets = repo.list_tickets()
    else:
        tickets = []
        for _code, r in _get_all_repos(state):
            tickets.extend(r.list_tickets())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID Tarea", "Titulo", "Estado", "Prioridad", "Notas", "Tags", "Creado", "Actualizado", "Cerrado"])
    for t in tickets:
        tags = json.loads(t.tags_json) if t.tags_json else []
        writer.writerow([
            t.ticket_id or "",
            t.title,
            t.status,
            t.priority,
            t.notes or "",
            ", ".join(tags),
            t.created_at,
            t.updated_at,
            t.closed_at or "",
        ])

    content = output.getvalue()
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kanban_export.csv"},
    )
