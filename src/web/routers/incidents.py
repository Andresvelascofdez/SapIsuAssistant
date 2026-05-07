"""Incident evidence router."""
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from src.incidents.storage.incident_repository import (
    Incident,
    IncidentEvidence,
    IncidentRepository,
    compute_sha256,
)
from src.web import dependencies as deps

log = logging.getLogger(__name__)
router = APIRouter()


def _repo_for_client(client_code: str) -> tuple[IncidentRepository | None, str | None]:
    code = (client_code or "").strip().upper()
    if not code:
        return None, "No client selected."
    cm = deps.get_client_manager()
    client = cm.get_client(code)
    if not client:
        return None, f"Client '{code}' is not registered."
    client_dir = cm.get_client_dir(client.code)
    client_dir.mkdir(parents=True, exist_ok=True)
    (client_dir / "incident_evidence").mkdir(exist_ok=True)
    return IncidentRepository(client_dir / "incidents.sqlite"), None


def _resolve_client_code(request: Request, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit.strip().upper()
    state = deps.get_state(request)
    return (state.active_client_code or "").strip().upper() or None


def _incident_to_dict(incident: Incident, evidence_count: int | None = None) -> dict:
    data = {
        "id": incident.id,
        "incident_code": incident.incident_code,
        "client_code": incident.client_code,
        "title": incident.title,
        "status": incident.status,
        "priority": incident.priority,
        "period_year": incident.period_year,
        "period_month": incident.period_month,
        "hours_spent": incident.hours_spent,
        "sap_module": incident.sap_module,
        "sap_process": incident.sap_process,
        "sap_objects": json.loads(incident.sap_objects_json or "[]"),
        "affected_ids": json.loads(incident.affected_ids_json or "[]"),
        "problem_statement": incident.problem_statement,
        "technical_uncertainty": incident.technical_uncertainty,
        "investigation": incident.investigation,
        "solution": incident.solution,
        "implementation_notes": incident.implementation_notes,
        "verification": incident.verification,
        "outcome": incident.outcome,
        "reusable_knowledge": incident.reusable_knowledge,
        "ipbox_relevance": incident.ipbox_relevance,
        "linked_kb_ids": json.loads(incident.linked_kb_ids_json or "[]"),
        "created_at": incident.created_at,
        "updated_at": incident.updated_at,
    }
    if evidence_count is not None:
        data["evidence_count"] = evidence_count
    return data


def _evidence_to_dict(evidence: IncidentEvidence) -> dict:
    return {
        "id": evidence.id,
        "incident_id": evidence.incident_id,
        "title": evidence.title,
        "kind": evidence.kind,
        "storage_path": evidence.storage_path,
        "url": evidence.url,
        "sha256": evidence.sha256,
        "original_file_name": evidence.original_file_name,
        "mime_type": evidence.mime_type,
        "size_bytes": evidence.size_bytes,
        "notes": evidence.notes,
        "created_at": evidence.created_at,
    }


def _get_repo_or_response(request: Request, explicit_client: str | None = None):
    code = _resolve_client_code(request, explicit_client)
    repo, error = _repo_for_client(code or "")
    if error:
        return None, code, JSONResponse({"error": error}, status_code=400)
    return repo, code, None


def _incident_has_kb_material(incident: Incident) -> bool:
    """Return True when the incident has enough narrative material for a KB draft."""
    if incident.status in ("RESOLVED", "CLOSED"):
        return True
    fields = [
        incident.problem_statement,
        incident.technical_uncertainty,
        incident.investigation,
        incident.solution,
        incident.implementation_notes,
        incident.verification,
        incident.outcome,
        incident.reusable_knowledge,
    ]
    return any((value or "").strip() for value in fields)


def _create_kb_draft_from_incident(repo: IncidentRepository, code: str, incident: Incident):
    from src.assistant.storage.kb_repository import KBItemRepository
    from src.assistant.storage.models import KBItemStatus, KBItemType

    cm = deps.get_client_manager()
    kb_repo = KBItemRepository(cm.get_client_dir(code) / "assistant_kb.sqlite")
    sap_objects = json.loads(incident.sap_objects_json or "[]")
    tags = ["SAP_ISU", "IPBOX_EVIDENCE"]
    for candidate in (incident.sap_module, incident.sap_process):
        if candidate:
            tags.append(candidate)
    item_type = (
        KBItemType.RESOLUTION
        if incident.status in ("RESOLVED", "CLOSED") or incident.solution
        else KBItemType.INCIDENT_PATTERN
    )
    content = _incident_to_markdown(incident)
    kb_item, _is_new = kb_repo.create_or_update(
        client_scope="client",
        client_code=code,
        item_type=item_type,
        title=f"{incident.incident_code} - {incident.title}",
        content_markdown=content,
        tags=tags,
        sap_objects=sap_objects,
        signals={
            "module": incident.sap_module,
            "process": incident.sap_process,
            "ipbox_relevance": incident.ipbox_relevance,
            "incident_code": incident.incident_code,
        },
        sources={
            "source": "incident",
            "incident_id": incident.id,
            "incident_code": incident.incident_code,
            "client_code": code,
        },
        status=KBItemStatus.DRAFT,
    )
    repo.link_kb_draft(incident.id, kb_item.kb_id)
    return kb_item


def _auto_create_kb_draft(repo: IncidentRepository, code: str, incident: Incident):
    """Create/update a DRAFT KB item for incidents that contain useful knowledge."""
    if not _incident_has_kb_material(incident):
        return None
    return _create_kb_draft_from_incident(repo, code, incident)


@router.get("/incidents")
async def incidents_page(request: Request):
    ctx = deps.get_template_context(request)
    return deps.templates.TemplateResponse(request, "incidents.html", ctx)


@router.get("/incidents/{incident_id}")
async def incident_detail_page(incident_id: str, request: Request):
    ctx = deps.get_template_context(request)
    ctx["incident_id"] = incident_id
    ctx["incident_client_code"] = request.query_params.get("client_code", "")
    return deps.templates.TemplateResponse(request, "incident_detail.html", ctx)


@router.get("/ipbox/dossier")
async def ipbox_dossier_page(request: Request):
    ctx = deps.get_template_context(request)
    ctx["current_year"] = datetime.now().year
    return deps.templates.TemplateResponse(request, "ipbox_dossier.html", ctx)


@router.get("/api/incidents")
async def list_incidents(
    request: Request,
    client_code: str | None = Query(default=None),
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    status: str | None = Query(default=None),
    ipbox_relevance: str | None = Query(default=None),
    search: str | None = Query(default=None),
):
    repo, _code, error = _get_repo_or_response(request, client_code)
    if error:
        return error
    incidents = repo.list_incidents(
        year=year,
        month=month,
        status=status,
        ipbox_relevance=ipbox_relevance,
        search=search,
    )
    return {
        "incidents": [
            _incident_to_dict(incident, evidence_count=len(repo.list_evidence(incident.id)))
            for incident in incidents
        ],
        "count": len(incidents),
    }


@router.post("/api/incidents")
async def create_incident(request: Request):
    body = await request.json()
    repo, code, error = _get_repo_or_response(request, body.get("client_code"))
    if error:
        return error
    try:
        incident = repo.create_incident(
            client_code=code,
            title=body.get("title", ""),
            period_year=body.get("period_year"),
            period_month=body.get("period_month"),
            status=body.get("status", "OPEN"),
            priority=body.get("priority", "MEDIUM"),
            hours_spent=body.get("hours_spent", 0.0),
            sap_module=body.get("sap_module"),
            sap_process=body.get("sap_process"),
            sap_objects=body.get("sap_objects"),
            affected_ids=body.get("affected_ids"),
            problem_statement=body.get("problem_statement"),
            technical_uncertainty=body.get("technical_uncertainty"),
            investigation=body.get("investigation"),
            solution=body.get("solution"),
            implementation_notes=body.get("implementation_notes"),
            verification=body.get("verification"),
            outcome=body.get("outcome"),
            reusable_knowledge=body.get("reusable_knowledge"),
            ipbox_relevance=body.get("ipbox_relevance", "UNCLEAR"),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    kb_item = _auto_create_kb_draft(repo, code, incident)
    incident = repo.get_incident(incident.id) or incident
    data = _incident_to_dict(incident, evidence_count=0)
    if kb_item:
        data["auto_kb_draft_id"] = kb_item.kb_id
    return data


@router.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str, request: Request, client_code: str | None = Query(default=None)):
    repo, _code, error = _get_repo_or_response(request, client_code)
    if error:
        return error
    incident = repo.get_incident(incident_id)
    if not incident:
        return JSONResponse({"error": "Incident not found."}, status_code=404)
    data = _incident_to_dict(incident, evidence_count=len(repo.list_evidence(incident_id)))
    data["evidence"] = [_evidence_to_dict(e) for e in repo.list_evidence(incident_id)]
    return data


@router.put("/api/incidents/{incident_id}")
async def update_incident(incident_id: str, request: Request):
    body = await request.json()
    repo, _code, error = _get_repo_or_response(request, body.get("client_code"))
    if error:
        return error
    updates = {
        key: value
        for key, value in body.items()
        if key
        in {
            "title",
            "status",
            "priority",
            "period_year",
            "period_month",
            "hours_spent",
            "sap_module",
            "sap_process",
            "sap_objects",
            "affected_ids",
            "problem_statement",
            "technical_uncertainty",
            "investigation",
            "solution",
            "implementation_notes",
            "verification",
            "outcome",
            "reusable_knowledge",
            "ipbox_relevance",
        }
    }
    try:
        incident = repo.update_incident(incident_id, **updates)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not incident:
        return JSONResponse({"error": "Incident not found."}, status_code=404)
    kb_item = _auto_create_kb_draft(repo, _code, incident)
    incident = repo.get_incident(incident_id) or incident
    data = _incident_to_dict(incident, evidence_count=len(repo.list_evidence(incident_id)))
    if kb_item:
        data["auto_kb_draft_id"] = kb_item.kb_id
    return data


@router.delete("/api/incidents/{incident_id}")
async def delete_incident(incident_id: str, request: Request, client_code: str | None = Query(default=None)):
    repo, _code, error = _get_repo_or_response(request, client_code)
    if error:
        return error
    evidence_items = repo.list_evidence(incident_id)
    if not repo.delete_incident(incident_id):
        return JSONResponse({"error": "Incident not found."}, status_code=404)
    for evidence in evidence_items:
        if evidence.storage_path:
            file_path = deps.DATA_ROOT / evidence.storage_path
            try:
                if file_path.exists():
                    file_path.unlink()
            except OSError:
                log.warning("Failed to delete evidence file: %s", file_path)
    return {"status": "deleted"}


@router.post("/api/incidents/{incident_id}/evidence")
async def add_evidence(
    incident_id: str,
    request: Request,
    title: str = Form(""),
    kind: str = Form("FILE"),
    url: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    client_code: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
):
    repo, code, error = _get_repo_or_response(request, client_code)
    if error:
        return error
    incident = repo.get_incident(incident_id)
    if not incident:
        return JSONResponse({"error": "Incident not found."}, status_code=404)

    storage_path = None
    sha256 = None
    original_name = None
    mime_type = None
    size_bytes = None
    normalized_kind = (kind or "FILE").strip().upper()

    try:
        if normalized_kind == "FILE":
            if not file:
                return JSONResponse({"error": "file is required for FILE evidence."}, status_code=400)
            content = await file.read()
            safe_name = Path(file.filename or "evidence.bin").name
            target_dir = deps.DATA_ROOT / "clients" / code / "incident_evidence" / incident_id
            target_dir.mkdir(parents=True, exist_ok=True)
            unique_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{safe_name}"
            dest = target_dir / unique_name
            dest.write_bytes(content)
            storage_path = dest.relative_to(deps.DATA_ROOT).as_posix()
            sha256 = compute_sha256(content)
            original_name = safe_name
            mime_type = file.content_type or "application/octet-stream"
            size_bytes = len(content)
            if not title:
                title = safe_name
        elif normalized_kind == "LINK" and not title and url:
            title = url
        elif normalized_kind == "NOTE" and not title:
            title = "Evidence note"
        evidence = repo.add_evidence(
            incident_id=incident_id,
            title=title,
            kind=normalized_kind,
            storage_path=storage_path,
            url=url,
            sha256=sha256,
            original_file_name=original_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            notes=notes,
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return _evidence_to_dict(evidence)


@router.delete("/api/incidents/{incident_id}/evidence/{evidence_id}")
async def delete_evidence(
    incident_id: str,
    evidence_id: str,
    request: Request,
    client_code: str | None = Query(default=None),
):
    repo, _code, error = _get_repo_or_response(request, client_code)
    if error:
        return error
    evidence = repo.get_evidence(evidence_id)
    if not evidence or evidence.incident_id != incident_id:
        return JSONResponse({"error": "Evidence not found."}, status_code=404)
    repo.delete_evidence(evidence_id)
    if evidence.storage_path:
        file_path = deps.DATA_ROOT / evidence.storage_path
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError:
            log.warning("Failed to delete evidence file: %s", file_path)
    return {"status": "deleted"}


@router.post("/api/incidents/{incident_id}/generate-kb-draft")
async def generate_kb_draft(incident_id: str, request: Request):
    body = await request.json()
    repo, code, error = _get_repo_or_response(request, body.get("client_code"))
    if error:
        return error
    incident = repo.get_incident(incident_id)
    if not incident:
        return JSONResponse({"error": "Incident not found."}, status_code=404)

    kb_item = _create_kb_draft_from_incident(repo, code, incident)
    return {
        "kb_id": kb_item.kb_id,
        "title": kb_item.title,
        "status": kb_item.status,
        "type": kb_item.type,
    }


@router.get("/api/ipbox/dossier")
async def generate_ipbox_dossier(year: int = Query(...)):
    cm = deps.get_client_manager()
    incidents_with_evidence: list[tuple[Incident, list[IncidentEvidence]]] = []
    for client in cm.list_clients():
        repo, error = _repo_for_client(client.code)
        if error or not repo:
            continue
        for incident in repo.list_incidents(year=year):
            incidents_with_evidence.append((incident, repo.list_evidence(incident.id)))

    incidents_with_evidence.sort(key=lambda pair: (pair[0].client_code, pair[0].incident_code))
    from src.incidents.pdf.ipbox_dossier import generate_ipbox_dossier_pdf

    out_dir = deps.DATA_ROOT / "ipbox" / "dossiers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ipbox_dossier_{year}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    generate_ipbox_dossier_pdf(year, incidents_with_evidence, out_path)
    return FileResponse(
        path=str(out_path),
        filename=f"sap_isu_ipbox_dossier_{year}.pdf",
        media_type="application/pdf",
    )


def _incident_to_markdown(incident: Incident) -> str:
    sap_objects = ", ".join(json.loads(incident.sap_objects_json or "[]")) or "N/A"
    affected_ids = ", ".join(json.loads(incident.affected_ids_json or "[]")) or "N/A"
    sections = [
        f"# {incident.title}",
        "",
        f"- Incident: {incident.incident_code}",
        f"- Client: {incident.client_code}",
        f"- Period: {incident.period_year}-{incident.period_month:02d}",
        f"- Status: {incident.status}",
        f"- Priority: {incident.priority}",
        f"- Hours: {incident.hours_spent:.2f}",
        f"- IP Box relevance: {incident.ipbox_relevance}",
        f"- SAP module: {incident.sap_module or 'N/A'}",
        f"- SAP process: {incident.sap_process or 'N/A'}",
        f"- SAP objects: {sap_objects}",
        f"- Affected IDs: {affected_ids}",
        "",
    ]
    for heading, value in [
        ("Problem Statement", incident.problem_statement),
        ("Technical Uncertainty", incident.technical_uncertainty),
        ("Investigation", incident.investigation),
        ("Solution", incident.solution),
        ("Implementation Notes", incident.implementation_notes),
        ("Verification", incident.verification),
        ("Outcome", incident.outcome),
        ("Reusable Knowledge", incident.reusable_knowledge),
    ]:
        if value:
            sections.extend([f"## {heading}", "", value, ""])
    return "\n".join(sections).strip()
