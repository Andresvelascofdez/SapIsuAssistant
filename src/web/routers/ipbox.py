"""IP Box usage evidence review routes."""
import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from src.ipbox.reporting import generate_monthly_ip_report
from src.ipbox.usage_logging import list_usage_events, update_usage_event
from src.web import dependencies as deps

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/ipbox/usage")
async def usage_evidence_page(request: Request):
    ctx = deps.get_template_context(request)
    return deps.templates.TemplateResponse(request, "ipbox_usage.html", ctx)


@router.get("/api/ipbox/usage-events")
async def usage_events(
    month: str | None = Query(default=None),
    client: str | None = Query(default=None),
    sap_module: str | None = Query(default=None),
    sap_process: str | None = Query(default=None),
    output_used: str | None = Query(default=None),
    delivery_used: str | None = Query(default=None),
    include_excluded: bool = Query(default=True),
):
    events = list_usage_events(
        deps.DATA_ROOT,
        month=month,
        client=client,
        sap_module=sap_module,
        sap_process=sap_process,
        output_used=output_used,
        delivery_used=delivery_used,
        include_excluded=include_excluded,
    )
    events.sort(key=lambda row: row.get("timestamp", ""), reverse=True)
    return {"events": events, "count": len(events)}


@router.put("/api/ipbox/usage-events/{usage_id}")
async def update_usage_event_api(usage_id: str, request: Request):
    body = await request.json()
    updated = update_usage_event(deps.DATA_ROOT, usage_id, body)
    if not updated:
        return JSONResponse({"error": "Usage event not found."}, status_code=404)
    return updated


@router.post("/api/ipbox/monthly-report")
async def monthly_report(request: Request):
    body = await request.json()
    month = (body.get("month") or "").strip()
    if not month:
        return JSONResponse({"error": "month is required in YYYY-MM format."}, status_code=400)
    try:
        summary, md_path, csv_path = generate_monthly_ip_report(
            deps.DATA_ROOT,
            deps.DATA_ROOT.parent / "reports",
            month,
            total_relevant_sap_isu_service_revenue=float(body.get("total_relevant_sap_isu_service_revenue") or 0),
            excluded_revenue=float(body.get("excluded_revenue") or 0),
            total_productive_sap_isu_hours=(
                float(body["total_productive_sap_isu_hours"])
                if body.get("total_productive_sap_isu_hours") not in (None, "")
                else None
            ),
            qualifying_service_factor=float(body.get("qualifying_service_factor") or 1.0),
        )
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    return {
        "summary": summary.__dict__,
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }


@router.get("/api/ipbox/monthly-report/download")
async def download_monthly_report(month: str = Query(...), kind: str = Query(default="md")):
    output_dir = deps.DATA_ROOT.parent / "reports" / "ip_box" / month
    path = output_dir / ("usage_events.csv" if kind == "csv" else "monthly_ip_usage_report.md")
    if not path.exists():
        return JSONResponse({"error": "Report not generated yet."}, status_code=404)
    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type="text/csv" if path.suffix == ".csv" else "text/markdown",
    )
