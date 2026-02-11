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
    cm = get_client_manager()
    client = cm.get_client(code)
    if not client:
        return None
    client_dir = state.data_root / "clients" / client.code
    client_dir.mkdir(parents=True, exist_ok=True)
    db_path = client_dir / "kanban.sqlite"
    return KanbanRepository(db_path, seed_columns=False)


def _get_kanban_repo_for_client(state, client_code: str):
    """Return a per-client KanbanRepository for an explicit client code.

    Validates client is registered and ensures directory exists.
    Returns (repo, None) on success or (None, error_msg) on failure.
    """
    from src.kanban.storage.kanban_repository import KanbanRepository
    if not client_code:
        return None, "No client selected."
    cm = get_client_manager()
    client = cm.get_client(client_code)
    if not client:
        return None, f"Client '{client_code}' is not registered."
    client_dir = state.data_root / "clients" / client.code
    client_dir.mkdir(parents=True, exist_ok=True)
    db_path = client_dir / "kanban.sqlite"
    return KanbanRepository(db_path, seed_columns=False), None


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


def _ticket_to_dict(t, client_code=None):
    d = {
        "id": t.id,
        "ticket_id": t.ticket_id,
        "title": t.title,
        "description": t.description,
        "status": t.status,
        "priority": t.priority,
        "notes": t.notes,
        "tags": json.loads(t.tags_json) if t.tags_json else [],
        "links": json.loads(t.links_json) if t.links_json else [],
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "closed_at": t.closed_at,
    }
    if client_code is not None:
        d["client_code"] = client_code
    return d


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
    active_code = (state.active_client_code or "").upper() or None

    if repo:
        tickets = repo.list_tickets(search=search, priority=priority, limit=limit, offset=offset)
        total = repo.count_tickets(search=search, priority=priority)
        ticket_dicts = [_ticket_to_dict(t, client_code=active_code) for t in tickets]
    else:
        all_tickets = []
        for code, r in _get_all_repos(state):
            for t in r.list_tickets(search=search, priority=priority):
                all_tickets.append((t, code))
        total = len(all_tickets)
        if limit is not None:
            all_tickets = all_tickets[offset:offset + limit]
        ticket_dicts = [_ticket_to_dict(t, client_code=c) for t, c in all_tickets]

    return {"tickets": ticket_dicts, "total": total}


@router.post("/api/kanban/tickets")
async def create_ticket(request: Request):
    state = get_state(request)
    body = await request.json()

    # Resolve client: explicit from body, or fall back to session
    client_code = body.get("client_code", "").strip()

    if client_code:
        repo, error = _get_kanban_repo_for_client(state, client_code)
        if error:
            return JSONResponse({"error": error}, status_code=400)
    else:
        repo = _get_kanban_repo(state)

    if not repo:
        return JSONResponse({"error": "No client selected. Select a client in the header or in the form."}, status_code=400)

    title = body.get("title", "").strip()
    if not title:
        return JSONResponse({"error": "Title is required."}, status_code=400)

    # Get default status from global columns
    global_repo = _get_global_repo(state)
    columns = global_repo.list_columns()
    default_status = columns[0].name if columns else "EN_PROGRESO"

    ticket = repo.create_ticket(
        title=title,
        ticket_id=body.get("ticket_id") or None,
        description=body.get("description") or None,
        priority=body.get("priority", "MEDIUM"),
        notes=body.get("notes") or None,
        tags=body.get("tags") or None,
        links=body.get("links") or None,
        status=body.get("status") or default_status,
    )
    return _ticket_to_dict(ticket)


@router.put("/api/kanban/tickets/{ticket_id}/move")
async def move_ticket(ticket_id: str, request: Request):
    state = get_state(request)
    body = await request.json()

    # Resolve repo: session client, or explicit client_code from body
    repo = _get_kanban_repo(state)
    if not repo:
        client_code = body.get("client_code", "").strip()
        if client_code:
            repo, error = _get_kanban_repo_for_client(state, client_code)
            if error:
                return JSONResponse({"error": error}, status_code=400)

    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

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
    body = await request.json()

    target_client = body.get("client_code", "").strip()
    source_client = body.get("source_client_code", "").strip()
    current_client = (state.active_client_code or "").strip().upper()

    # Resolve source repo: session client, or source_client_code, or client_code
    repo = _get_kanban_repo(state)
    if not repo and (source_client or target_client):
        source_code = source_client or target_client
        repo, error = _get_kanban_repo_for_client(state, source_code)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        current_client = source_code.upper()

    if not repo:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    target_client_upper = target_client.upper() if target_client else ""

    if target_client and target_client_upper != current_client:
        # Moving ticket to a different client
        old_ticket = repo.get_by_id(ticket_id)
        if not old_ticket:
            return JSONResponse({"error": "Ticket not found."}, status_code=404)

        target_repo, error = _get_kanban_repo_for_client(state, target_client)
        if error:
            return JSONResponse({"error": error}, status_code=400)

        # Create in target DB with updated fields
        tags_data = body.get("tags") if body.get("tags") is not None else (json.loads(old_ticket.tags_json) if old_ticket.tags_json else None)
        links_data = body.get("links") if body.get("links") is not None else (json.loads(old_ticket.links_json) if old_ticket.links_json else None)

        new_ticket = target_repo.create_ticket(
            title=body.get("title") or old_ticket.title,
            ticket_id=body.get("ticket_id") if body.get("ticket_id") is not None else old_ticket.ticket_id,
            description=body.get("description") if body.get("description") is not None else old_ticket.description,
            priority=body.get("priority") or old_ticket.priority,
            notes=body.get("notes") if body.get("notes") is not None else old_ticket.notes,
            tags=tags_data,
            links=links_data,
            status=old_ticket.status,
        )

        repo.delete_ticket(ticket_id)
        return _ticket_to_dict(new_ticket)

    # Normal update (same client)
    ticket = repo.update_ticket(
        ticket_id,
        title=body.get("title"),
        ticket_id=body.get("ticket_id"),
        description=body.get("description"),
        priority=body.get("priority"),
        notes=body.get("notes"),
        tags=body.get("tags"),
        links=body.get("links"),
    )
    if not ticket:
        return JSONResponse({"error": "Ticket not found."}, status_code=404)
    return _ticket_to_dict(ticket)


@router.get("/api/kanban/tickets/{ticket_id}/history")
async def ticket_history(ticket_id: str, request: Request, client_code: str = Query(default=None)):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo and client_code:
        repo, error = _get_kanban_repo_for_client(state, client_code.strip())
        if error:
            return JSONResponse({"error": error}, status_code=400)
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
async def delete_ticket(ticket_id: str, request: Request, client_code: str = Query(default=None)):
    state = get_state(request)
    repo = _get_kanban_repo(state)
    if not repo and client_code:
        repo, error = _get_kanban_repo_for_client(state, client_code.strip())
        if error:
            return JSONResponse({"error": error}, status_code=400)
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
    writer.writerow(["ID Tarea", "Titulo", "Descripcion", "Estado", "Prioridad", "Notas", "Tags", "Creado", "Actualizado", "Cerrado"])
    for t in tickets:
        tags = json.loads(t.tags_json) if t.tags_json else []
        writer.writerow([
            t.ticket_id or "",
            t.title,
            t.description or "",
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
