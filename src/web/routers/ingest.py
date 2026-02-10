"""Ingest router with file upload and background synthesis."""
import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse

from src.web.dependencies import (
    get_state, get_openai_api_key, get_client_manager, get_template_context, templates, DATA_ROOT,
)

log = logging.getLogger(__name__)
router = APIRouter()

# In-memory status tracker for background ingestions
_ingestion_status: dict[str, dict] = {}


def _run_synthesis(ingestion_id: str, text: str, scope: str, client_code: str | None, api_key: str | None):
    """Background task: synthesize text and store KB items."""
    from src.assistant.ingestion.synthesis import SynthesisPipeline, SynthesisError
    from src.assistant.storage.ingestion_repository import IngestionRepository
    from src.assistant.storage.kb_repository import KBItemRepository
    from src.assistant.storage.models import KBItemType, KBItemStatus, IngestionStatus

    cm = get_client_manager()
    if scope == "standard":
        db_path = cm.get_standard_dir() / "assistant_kb.sqlite"
    else:
        db_path = cm.get_client_dir(client_code) / "assistant_kb.sqlite"

    ing_repo = IngestionRepository(db_path)
    kb_repo = KBItemRepository(db_path)

    try:
        _ingestion_status[ingestion_id]["status"] = "synthesizing"

        pipeline = SynthesisPipeline(api_key=api_key)
        result = pipeline.synthesize(text)
        items = result.get("kb_items", [])

        ing_repo.update_status(ingestion_id, IngestionStatus.SYNTHESIZED)

        stored = 0
        for synth_item in items:
            try:
                kb_repo.create_or_update(
                    client_scope=scope,
                    client_code=client_code,
                    item_type=KBItemType(synth_item["type"]),
                    title=synth_item["title"],
                    content_markdown=synth_item["content_markdown"],
                    tags=synth_item.get("tags", []),
                    sap_objects=synth_item.get("sap_objects", []),
                    signals=synth_item.get("signals", {}),
                    sources={"ingestion_id": ingestion_id},
                )
                stored += 1
            except Exception as e:
                log.warning("Failed to store KB item: %s", e)

        _ingestion_status[ingestion_id].update({
            "status": "completed",
            "items_count": stored,
        })
    except SynthesisError as e:
        log.exception("Synthesis failed")
        ing_repo.update_status(ingestion_id, IngestionStatus.FAILED)
        _ingestion_status[ingestion_id].update({"status": "failed", "error": str(e)})
    except Exception as e:
        log.exception("Ingestion error")
        _ingestion_status[ingestion_id].update({"status": "failed", "error": str(e)})


@router.get("/ingest")
async def ingest_page(request: Request):
    ctx = get_template_context(request)
    return templates.TemplateResponse("ingest.html", ctx)


@router.post("/api/ingest/text")
async def ingest_text(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    text = body.get("text", "").strip()
    scope = body.get("scope", "standard")

    if not text:
        return JSONResponse({"error": "Text is empty."}, status_code=400)

    state = get_state(request)
    client_code = state.active_client_code if scope == "client" else None
    if scope == "client" and not client_code:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    api_key = get_openai_api_key(request)

    from src.assistant.ingestion.extractors import extract_text
    from src.assistant.storage.ingestion_repository import IngestionRepository

    result = extract_text(text, label="web-input")

    cm = get_client_manager()
    if scope == "standard":
        db_path = cm.get_standard_dir() / "assistant_kb.sqlite"
    else:
        db_path = cm.get_client_dir(client_code) / "assistant_kb.sqlite"

    ing_repo = IngestionRepository(db_path)
    ingestion = ing_repo.create(
        client_scope=scope,
        client_code=client_code,
        input_kind=result.input_kind,
        input_hash=result.input_hash,
        input_name=result.input_name,
        model_used="gpt-5.2",
        reasoning_effort="xhigh",
    )

    _ingestion_status[ingestion.ingestion_id] = {"status": "queued", "items_count": 0, "error": None}
    background_tasks.add_task(_run_synthesis, ingestion.ingestion_id, result.text, scope, client_code, api_key)

    return JSONResponse({"ingestion_id": ingestion.ingestion_id, "status": "queued"}, status_code=202)


@router.post("/api/ingest/file")
async def ingest_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    scope: str = Form("standard"),
):
    state = get_state(request)
    client_code = state.active_client_code if scope == "client" else None
    if scope == "client" and not client_code:
        return JSONResponse({"error": "No client selected."}, status_code=400)

    api_key = get_openai_api_key(request)

    # Save upload to temp location
    cm = get_client_manager()
    if scope == "standard":
        upload_dir = cm.get_standard_dir() / "uploads"
    else:
        upload_dir = cm.get_client_dir(client_code) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest_path = upload_dir / file.filename
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Extract text
    from src.assistant.ingestion.extractors import extract_pdf, extract_docx
    from src.assistant.storage.ingestion_repository import IngestionRepository

    suffix = dest_path.suffix.lower()
    if suffix == ".pdf":
        result = extract_pdf(dest_path)
    elif suffix in (".docx", ".doc"):
        result = extract_docx(dest_path)
    else:
        return JSONResponse({"error": f"Unsupported file type: {suffix}"}, status_code=400)

    if scope == "standard":
        db_path = cm.get_standard_dir() / "assistant_kb.sqlite"
    else:
        db_path = cm.get_client_dir(client_code) / "assistant_kb.sqlite"

    ing_repo = IngestionRepository(db_path)
    ingestion = ing_repo.create(
        client_scope=scope,
        client_code=client_code,
        input_kind=result.input_kind,
        input_hash=result.input_hash,
        input_name=result.input_name,
        model_used="gpt-5.2",
        reasoning_effort="xhigh",
    )

    _ingestion_status[ingestion.ingestion_id] = {"status": "queued", "items_count": 0, "error": None}
    background_tasks.add_task(_run_synthesis, ingestion.ingestion_id, result.text, scope, client_code, api_key)

    return JSONResponse({"ingestion_id": ingestion.ingestion_id, "status": "queued"}, status_code=202)


@router.get("/api/ingest/{ingestion_id}/status")
async def ingestion_status(ingestion_id: str):
    status = _ingestion_status.get(ingestion_id)
    if not status:
        return JSONResponse({"error": "Ingestion not found."}, status_code=404)
    return status
