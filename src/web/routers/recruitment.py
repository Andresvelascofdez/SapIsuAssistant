"""Recruitment candidate database routes."""
from __future__ import annotations

import os
import platform
import subprocess
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse

from core.recruitment.candidate_manager import CandidateManager, CandidateValidationError
from core.recruitment.cv_autofill import autofill_from_text
from core.recruitment.cv_parser import SUPPORTED_EXTENSIONS, import_cv
from src.web import dependencies as deps

router = APIRouter()


def _manager() -> CandidateManager:
    return CandidateManager(deps.DATA_ROOT)


def _candidate_to_dict(candidate) -> dict:
    return candidate.to_dict()


def _filters_from_request(request: Request) -> dict:
    params = request.query_params
    return {
        "cv_text": params.get("cv_text"),
        "skill_text": params.get("skill_text"),
        "sap_module_text": params.get("sap_module_text"),
        "language_text": params.get("language_text"),
        "country": params.get("country"),
        "seniority": params.get("seniority"),
        "work_mode": params.get("work_mode"),
        "max_hourly_rate": params.get("max_hourly_rate"),
        "max_daily_rate": params.get("max_daily_rate"),
    }


@router.get("/recruitment")
async def recruitment_page(request: Request):
    ctx = deps.get_template_context(request)
    return deps.templates.TemplateResponse(request, "recruitment.html", ctx)


@router.get("/api/recruitment/candidates")
async def list_candidates(request: Request):
    manager = _manager()
    search = request.query_params.get("search") or ""
    candidates = manager.list_candidates(search=search, filters=_filters_from_request(request))
    return {
        "count": len(candidates),
        "candidates": [_candidate_to_dict(candidate) for candidate in candidates],
    }


@router.get("/api/recruitment/candidates/{candidate_id}")
async def get_candidate(candidate_id: int):
    candidate = _manager().get_candidate(candidate_id)
    if not candidate:
        return JSONResponse({"error": "Candidate not found."}, status_code=404)
    return _candidate_to_dict(candidate)


@router.post("/api/recruitment/candidates")
async def create_candidate(request: Request):
    payload = await request.json()
    try:
        candidate = _manager().create_candidate(payload)
    except CandidateValidationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return _candidate_to_dict(candidate)


@router.put("/api/recruitment/candidates/{candidate_id}")
async def update_candidate(candidate_id: int, request: Request):
    payload = await request.json()
    try:
        candidate = _manager().update_candidate(candidate_id, payload)
    except CandidateValidationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except KeyError:
        return JSONResponse({"error": "Candidate not found."}, status_code=404)
    return _candidate_to_dict(candidate)


@router.delete("/api/recruitment/candidates/{candidate_id}")
async def delete_candidate(candidate_id: int):
    deleted = _manager().delete_candidate(candidate_id)
    if not deleted:
        return JSONResponse({"error": "Candidate not found."}, status_code=404)
    return {"deleted": True}


@router.post("/api/recruitment/cv/import")
async def import_candidate_cv(file: UploadFile = File(...)):
    filename = file.filename or "cv"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return JSONResponse(
            {"error": "Unsupported CV file type. Use PDF, DOC, DOCX or TXT."},
            status_code=400,
        )

    tmp_dir = deps.DATA_ROOT / "recruitment" / "tmp_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name.replace("/", "_").replace("\\", "_")
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}_{safe_name}"
    try:
        tmp_path.write_bytes(await file.read())
        imported = import_cv(tmp_path, data_root=deps.DATA_ROOT)
    finally:
        tmp_path.unlink(missing_ok=True)

    autofill = autofill_from_text(imported.get("cv_text") or "", filename_hint=filename)
    return {
        "candidate": {
            **autofill,
            "cv_file_path": imported["cv_file_path"],
            "cv_text": imported["cv_text"],
        },
        "error": imported.get("error"),
        "saved": False,
    }


@router.post("/api/recruitment/candidates/{candidate_id}/open-cv")
async def open_candidate_cv(candidate_id: int):
    candidate = _manager().get_candidate(candidate_id)
    if not candidate:
        return JSONResponse({"error": "Candidate not found."}, status_code=404)
    cv_path = Path(candidate.cv_file_path or "")
    if not cv_path.exists() or not cv_path.is_file():
        return JSONResponse({"error": "CV file is missing or has not been imported."}, status_code=404)
    try:
        if platform.system() == "Windows":
            os.startfile(cv_path)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(cv_path)])
        else:
            subprocess.Popen(["xdg-open", str(cv_path)])
    except Exception as exc:
        return JSONResponse({"error": f"Could not open CV file: {exc}"}, status_code=500)
    return {"opened": True}
