"""Finance router - settings, categories, documents, expenses, invoices endpoints."""
import csv
import io
import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query, Request, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse

from src.web.dependencies import get_finance_repository, get_template_context, templates, DATA_ROOT

log = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_ROOT = DATA_ROOT / "finance" / "uploads"


def _settings_to_dict(s):
    return {
        "id": s.id,
        "tax_rate_default": s.tax_rate_default,
        "company_name": s.company_name,
        "company_address": s.company_address,
        "company_tax_id": s.company_tax_id,
        "company_email": s.company_email,
        "company_phone": s.company_phone,
        "company_bank_details": s.company_bank_details,
        "updated_at": s.updated_at,
    }


def _category_to_dict(c):
    return {"id": c.id, "name": c.name, "is_active": c.is_active, "sort_order": c.sort_order}


def _document_to_dict(d):
    return {
        "id": d.id,
        "original_file_name": d.original_file_name,
        "mime_type": d.mime_type,
        "size_bytes": d.size_bytes,
        "sha256": d.sha256,
        "ocr_raw_text": d.ocr_raw_text,
        "ocr_detected_amount": d.ocr_detected_amount,
        "ocr_detected_date_iso": d.ocr_detected_date_iso,
        "created_at": d.created_at,
    }


def _expense_to_dict(e):
    return {
        "id": e.id,
        "period_year": e.period_year,
        "period_month": e.period_month,
        "category_id": e.category_id,
        "category_name": e.category_name,
        "merchant": e.merchant,
        "amount": e.amount,
        "currency": e.currency,
        "notes": e.notes,
        "document_id": e.document_id,
        "document_not_required": e.document_not_required,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
    }


# ── Pages ──

@router.get("/finance/expenses")
async def expenses_page(request: Request):
    ctx = get_template_context(request)
    return templates.TemplateResponse("finance_expenses.html", ctx)


@router.get("/finance/settings")
async def finance_settings_page(request: Request):
    ctx = get_template_context(request)
    return templates.TemplateResponse("finance_settings.html", ctx)


# ── Settings API ──

@router.get("/api/finance/settings")
async def get_settings():
    repo = get_finance_repository()
    return _settings_to_dict(repo.get_settings())


@router.put("/api/finance/settings")
async def update_settings(request: Request):
    body = await request.json()
    repo = get_finance_repository()
    s = repo.update_settings(**body)
    return _settings_to_dict(s)


# ── Categories API ──

@router.get("/api/finance/categories")
async def list_categories(active_only: bool = Query(default=True)):
    repo = get_finance_repository()
    cats = repo.list_categories(active_only=active_only)
    return [_category_to_dict(c) for c in cats]


@router.post("/api/finance/categories")
async def create_category(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "Name is required."}, status_code=400)
    repo = get_finance_repository()
    try:
        cat = repo.create_category(name)
        return _category_to_dict(cat)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.put("/api/finance/categories/reorder")
async def reorder_categories(request: Request):
    body = await request.json()
    ordered_ids = body.get("ordered_ids", [])
    if not ordered_ids:
        return JSONResponse({"error": "ordered_ids is required."}, status_code=400)
    repo = get_finance_repository()
    cats = repo.reorder_categories(ordered_ids)
    return [_category_to_dict(c) for c in cats]


@router.put("/api/finance/categories/{cat_id}")
async def rename_category(cat_id: int, request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "Name is required."}, status_code=400)
    repo = get_finance_repository()
    cat = repo.rename_category(cat_id, name)
    if not cat:
        return JSONResponse({"error": "Category not found."}, status_code=404)
    return _category_to_dict(cat)


@router.put("/api/finance/categories/{cat_id}/toggle")
async def toggle_category(cat_id: int, request: Request):
    body = await request.json()
    active = body.get("active", True)
    repo = get_finance_repository()
    cat = repo.toggle_category(cat_id, active)
    if not cat:
        return JSONResponse({"error": "Category not found."}, status_code=404)
    return _category_to_dict(cat)


@router.delete("/api/finance/categories/{cat_id}")
async def delete_category(cat_id: int):
    repo = get_finance_repository()
    try:
        deleted = repo.delete_category(cat_id)
        if not deleted:
            return JSONResponse({"error": "Category not found."}, status_code=404)
        return {"status": "ok"}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ── Documents API ──

@router.post("/api/finance/upload")
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()
    now = datetime.now()
    folder = UPLOAD_ROOT / str(now.year) / f"{now.month:02d}"
    folder.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name if file.filename else "upload"
    dest = folder / f"{now.strftime('%Y%m%d_%H%M%S')}_{safe_name}"
    dest.write_bytes(content)

    repo = get_finance_repository()
    doc = repo.create_document(
        original_file_name=safe_name,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        storage_path=str(dest.relative_to(DATA_ROOT)),
        file_bytes=content,
    )
    return _document_to_dict(doc)


@router.get("/api/finance/documents/{doc_id}/download")
async def download_document(doc_id: str):
    repo = get_finance_repository()
    doc = repo.get_document(doc_id)
    if not doc:
        return JSONResponse({"error": "Document not found."}, status_code=404)
    file_path = DATA_ROOT / doc.storage_path
    if not file_path.exists():
        return JSONResponse({"error": "File not found on disk."}, status_code=404)
    return FileResponse(
        path=str(file_path),
        filename=doc.original_file_name,
        media_type=doc.mime_type,
    )


@router.delete("/api/finance/documents/{doc_id}")
async def delete_document(doc_id: str):
    repo = get_finance_repository()
    doc = repo.get_document(doc_id)
    if not doc:
        return JSONResponse({"error": "Document not found."}, status_code=404)
    # Delete file from disk
    file_path = DATA_ROOT / doc.storage_path
    if file_path.exists():
        file_path.unlink()
    repo.delete_document(doc_id)
    return {"status": "ok"}


# ── Expenses API ──

@router.get("/api/finance/expenses")
async def list_expenses(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    category_id: int | None = Query(default=None),
    limit: int | None = Query(default=None),
    offset: int = Query(default=0),
):
    repo = get_finance_repository()
    expenses = repo.list_expenses(year=year, month=month, category_id=category_id, limit=limit, offset=offset)
    total = repo.sum_expenses(year=year, month=month)
    count = repo.count_expenses(year=year, month=month, category_id=category_id)
    return {
        "expenses": [_expense_to_dict(e) for e in expenses],
        "total": total,
        "count": count,
    }


@router.post("/api/finance/expenses")
async def create_expense(request: Request):
    body = await request.json()
    required = ["period_year", "period_month", "category_id", "amount"]
    for field in required:
        if field not in body:
            return JSONResponse({"error": f"{field} is required."}, status_code=400)
    repo = get_finance_repository()
    expense = repo.create_expense(
        period_year=body["period_year"],
        period_month=body["period_month"],
        category_id=body["category_id"],
        amount=body["amount"],
        merchant=body.get("merchant"),
        notes=body.get("notes"),
        document_id=body.get("document_id"),
        document_not_required=body.get("document_not_required", False),
    )
    return _expense_to_dict(expense)


@router.put("/api/finance/expenses/{expense_id}")
async def update_expense(expense_id: str, request: Request):
    body = await request.json()
    repo = get_finance_repository()
    expense = repo.update_expense(expense_id, **body)
    if not expense:
        return JSONResponse({"error": "Expense not found."}, status_code=404)
    return _expense_to_dict(expense)


@router.delete("/api/finance/expenses/{expense_id}")
async def delete_expense(expense_id: str):
    repo = get_finance_repository()
    deleted = repo.delete_expense(expense_id)
    if not deleted:
        return JSONResponse({"error": "Expense not found."}, status_code=404)
    return {"status": "ok"}


@router.get("/api/finance/expenses/export-csv")
async def export_expenses_csv(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
):
    repo = get_finance_repository()
    expenses = repo.list_expenses(year=year, month=month)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Period", "Category", "Merchant", "Amount", "Currency", "Notes", "Has Document"])
    for e in expenses:
        writer.writerow([
            f"{e.period_year}-{e.period_month:02d}",
            e.category_name,
            e.merchant or "",
            f"{e.amount:.2f}",
            e.currency,
            e.notes or "",
            "Yes" if e.document_id else ("N/A" if e.document_not_required else "MISSING"),
        ])
    output.seek(0)
    filename = "expenses"
    if year:
        filename += f"_{year}"
    if month:
        filename += f"_{month:02d}"
    filename += ".csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Invoice helpers ──

def _invoice_to_dict(inv):
    return {
        "id": inv.id,
        "period_year": inv.period_year,
        "period_month": inv.period_month,
        "client_name": inv.client_name,
        "client_address": inv.client_address,
        "invoice_number": inv.invoice_number,
        "status": inv.status,
        "currency": inv.currency,
        "vat_rate": inv.vat_rate,
        "subtotal": inv.subtotal,
        "vat_amount": inv.vat_amount,
        "total": inv.total,
        "notes": inv.notes,
        "document_id": inv.document_id,
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
    }


def _invoice_item_to_dict(item):
    return {
        "id": item.id,
        "invoice_id": item.invoice_id,
        "description": item.description,
        "quantity": item.quantity,
        "unit": item.unit,
        "unit_price": item.unit_price,
        "line_total": item.line_total,
    }


# ── Invoice Pages ──

@router.get("/finance/invoices")
async def invoices_page(request: Request):
    ctx = get_template_context(request)
    return templates.TemplateResponse("finance_invoices.html", ctx)


@router.get("/finance/invoices/new")
async def invoice_new_page(request: Request):
    ctx = get_template_context(request)
    ctx["invoice_id"] = None
    return templates.TemplateResponse("finance_invoice_edit.html", ctx)


@router.get("/finance/invoices/{invoice_id}/edit")
async def invoice_edit_page(invoice_id: str, request: Request):
    ctx = get_template_context(request)
    ctx["invoice_id"] = invoice_id
    return templates.TemplateResponse("finance_invoice_edit.html", ctx)


# ── Invoices API ──

@router.get("/api/finance/invoices/export-csv")
async def export_invoices_csv(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
):
    repo = get_finance_repository()
    invoices = repo.list_invoices(year=year, month=month)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Period", "Client", "Invoice No", "Status", "VAT%", "Subtotal", "VAT", "Total", "Currency"])
    for inv in invoices:
        writer.writerow([
            f"{inv.period_year}-{inv.period_month:02d}",
            inv.client_name,
            inv.invoice_number,
            inv.status,
            f"{inv.vat_rate * 100:.1f}",
            f"{inv.subtotal:.2f}",
            f"{inv.vat_amount:.2f}",
            f"{inv.total:.2f}",
            inv.currency,
        ])
    output.seek(0)
    filename = "invoices"
    if year:
        filename += f"_{year}"
    if month:
        filename += f"_{month:02d}"
    filename += ".csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/api/finance/invoices")
async def list_invoices(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    client: str | None = Query(default=None),
):
    repo = get_finance_repository()
    invoices = repo.list_invoices(year=year, month=month, client=client)
    total = repo.sum_invoices(year=year, month=month)
    pending = repo.sum_pending_invoices(year=year, month=month)
    count = repo.count_invoices(year=year, month=month)
    return {
        "invoices": [_invoice_to_dict(inv) for inv in invoices],
        "total": total,
        "pending": pending,
        "count": count,
    }


@router.post("/api/finance/invoices")
async def create_invoice(request: Request):
    body = await request.json()
    required = ["period_year", "period_month", "client_name", "invoice_number"]
    for field in required:
        if field not in body or not body[field]:
            return JSONResponse({"error": f"{field} is required."}, status_code=400)
    repo = get_finance_repository()
    invoice = repo.create_invoice(
        period_year=body["period_year"],
        period_month=body["period_month"],
        client_name=body["client_name"],
        invoice_number=body["invoice_number"],
        client_address=body.get("client_address"),
        status=body.get("status", "PENDING"),
        vat_rate=body.get("vat_rate", 0.0),
        notes=body.get("notes"),
        document_id=body.get("document_id"),
        items=body.get("items", []),
    )
    return _invoice_to_dict(invoice)


@router.get("/api/finance/invoices/{invoice_id}")
async def get_invoice(invoice_id: str):
    repo = get_finance_repository()
    invoice = repo.get_invoice(invoice_id)
    if not invoice:
        return JSONResponse({"error": "Invoice not found."}, status_code=404)
    items = repo.get_invoice_items(invoice_id)
    result = _invoice_to_dict(invoice)
    result["items"] = [_invoice_item_to_dict(i) for i in items]
    return result


@router.put("/api/finance/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, request: Request):
    body = await request.json()
    repo = get_finance_repository()
    # Handle items separately
    items = body.pop("items", None)
    invoice = repo.update_invoice(invoice_id, **body)
    if not invoice:
        return JSONResponse({"error": "Invoice not found."}, status_code=404)
    if items is not None:
        repo.set_invoice_items(invoice_id, items)
        invoice = repo.get_invoice(invoice_id)
    result = _invoice_to_dict(invoice)
    result["items"] = [_invoice_item_to_dict(i) for i in repo.get_invoice_items(invoice_id)]
    return result


@router.delete("/api/finance/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str):
    repo = get_finance_repository()
    deleted = repo.delete_invoice(invoice_id)
    if not deleted:
        return JSONResponse({"error": "Invoice not found."}, status_code=404)
    return {"status": "ok"}


@router.post("/api/finance/invoices/{invoice_id}/generate-pdf")
async def generate_invoice_pdf_endpoint(invoice_id: str):
    repo = get_finance_repository()
    invoice = repo.get_invoice(invoice_id)
    if not invoice:
        return JSONResponse({"error": "Invoice not found."}, status_code=404)
    items = repo.get_invoice_items(invoice_id)
    settings = repo.get_settings()

    # Generate PDF
    from src.finance.pdf.invoice_pdf import generate_invoice_pdf
    pdf_folder = DATA_ROOT / "finance" / "invoices"
    pdf_folder.mkdir(parents=True, exist_ok=True)
    pdf_name = f"{invoice.invoice_number}_{invoice.period_year}_{invoice.period_month:02d}.pdf"
    pdf_path = pdf_folder / pdf_name
    generate_invoice_pdf(invoice, items, settings, pdf_path)

    # Create document record
    content = pdf_path.read_bytes()
    doc = repo.create_document(
        original_file_name=pdf_name,
        mime_type="application/pdf",
        size_bytes=len(content),
        storage_path=str(pdf_path.relative_to(DATA_ROOT)),
        file_bytes=content,
    )
    # Attach to invoice
    repo.update_invoice(invoice_id, document_id=doc.id)
    updated = repo.get_invoice(invoice_id)
    result = _invoice_to_dict(updated)
    result["items"] = [_invoice_item_to_dict(i) for i in items]
    return result
