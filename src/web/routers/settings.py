"""Settings router."""
import json
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.web.dependencies import get_state, get_client_manager, get_template_context, templates

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/settings")
async def settings_page(request: Request):
    ctx = get_template_context(request)
    cm = get_client_manager()
    ctx["client_list"] = [{"code": c.code, "name": c.name} for c in cm.list_clients()]
    return templates.TemplateResponse("settings.html", ctx)


@router.post("/api/settings/client")
async def register_client(request: Request):
    body = await request.json()
    code = body.get("code", "").strip()
    name = body.get("name", "").strip()
    if not code or not name:
        return JSONResponse({"error": "Code and name are required."}, status_code=400)
    try:
        cm = get_client_manager()
        client = cm.register_client(code, name)
        return {"code": client.code, "name": client.name}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get("/api/settings/clients")
async def list_clients(request: Request):
    cm = get_client_manager()
    return [{"code": c.code, "name": c.name} for c in cm.list_clients()]


@router.post("/api/settings/qdrant")
async def set_qdrant_url(request: Request):
    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        return JSONResponse({"error": "URL is required."}, status_code=400)
    request.session["qdrant_url"] = url
    return {"qdrant_url": url}


@router.post("/api/settings/apikey")
async def set_api_key(request: Request):
    body = await request.json()
    key = body.get("key", "").strip()
    if not key:
        return JSONResponse({"error": "API key is required."}, status_code=400)
    request.session["openai_api_key"] = key
    os.environ["OPENAI_API_KEY"] = key
    return {"status": "ok"}


@router.post("/api/session/client")
async def set_active_client(request: Request):
    body = await request.json()
    code = body.get("code")
    request.session["active_client_code"] = code if code else None
    return {"active_client_code": code}


@router.post("/api/session/standard-kb")
async def toggle_standard_kb(request: Request):
    body = await request.json()
    enabled = body.get("enabled", True)
    request.session["standard_kb_enabled"] = enabled
    return {"standard_kb_enabled": enabled}


@router.post("/api/settings/stale-days")
async def set_stale_days(request: Request):
    body = await request.json()
    days = body.get("days")
    if not isinstance(days, int) or days < 1:
        return JSONResponse({"error": "days must be a positive integer."}, status_code=400)
    request.session["stale_ticket_days"] = days
    return {"status": "ok", "days": days}
