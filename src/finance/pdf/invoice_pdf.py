"""Invoice PDF generation using reportlab."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from src.finance.storage.finance_repository import Invoice, InvoiceItem, FinanceSettings


def generate_invoice_pdf(
    invoice: Invoice,
    items: list[InvoiceItem],
    settings: FinanceSettings,
    output_path: Path,
) -> Path:
    """Generate a PDF invoice and save to output_path. Returns the path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle", parent=styles["Title"], fontSize=24, spaceAfter=6 * mm,
    )
    heading_style = ParagraphStyle(
        "SectionHeading", parent=styles["Heading3"], fontSize=11,
        spaceBefore=4 * mm, spaceAfter=2 * mm,
    )
    normal_style = styles["Normal"]
    small_style = ParagraphStyle(
        "Small", parent=normal_style, fontSize=9, textColor=colors.grey,
    )

    elements = []

    # Title
    elements.append(Paragraph("INVOICE", title_style))

    # Invoice metadata
    meta_data = [
        ["Invoice No:", invoice.invoice_number],
        ["Date:", f"{invoice.period_month:02d}/{invoice.period_year}"],
        ["Status:", invoice.status],
    ]
    if invoice.vat_rate > 0:
        meta_data.append(["VAT Rate:", f"{invoice.vat_rate * 100:.1f}%"])

    meta_table = Table(meta_data, colWidths=[30 * mm, 50 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 6 * mm))

    # From / Bill To
    from_lines = []
    if settings.company_name:
        from_lines.append(settings.company_name)
    if settings.company_address:
        from_lines.append(settings.company_address)
    if settings.company_tax_id:
        from_lines.append(f"Tax ID: {settings.company_tax_id}")
    if settings.company_email:
        from_lines.append(settings.company_email)
    if settings.company_phone:
        from_lines.append(settings.company_phone)

    to_lines = [invoice.client_name]
    if invoice.client_address:
        to_lines.append(invoice.client_address)

    addr_data = [
        [Paragraph("<b>From:</b>", normal_style), Paragraph("<b>Bill To:</b>", normal_style)],
        [Paragraph("<br/>".join(from_lines), small_style) if from_lines else "",
         Paragraph("<br/>".join(to_lines), small_style)],
    ]
    addr_table = Table(addr_data, colWidths=[85 * mm, 85 * mm])
    addr_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(addr_table)
    elements.append(Spacer(1, 8 * mm))

    # Items table
    elements.append(Paragraph("Items", heading_style))
    header = ["Description", "Qty", "Unit", "Unit Price", "Total"]
    table_data = [header]
    for item in items:
        table_data.append([
            item.description,
            f"{item.quantity:.2f}",
            item.unit,
            f"{item.unit_price:.2f}",
            f"{item.line_total:.2f}",
        ])

    col_widths = [80 * mm, 20 * mm, 20 * mm, 25 * mm, 25 * mm]
    items_table = Table(table_data, colWidths=col_widths)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 4 * mm))

    # Totals
    totals_data = [
        ["Subtotal:", f"{invoice.subtotal:.2f} {invoice.currency}"],
    ]
    if invoice.vat_rate > 0:
        totals_data.append([f"VAT ({invoice.vat_rate * 100:.1f}%):", f"{invoice.vat_amount:.2f} {invoice.currency}"])
    totals_data.append(["Total:", f"{invoice.total:.2f} {invoice.currency}"])

    totals_table = Table(totals_data, colWidths=[130 * mm, 40 * mm])
    totals_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(totals_table)

    # Notes
    if invoice.notes:
        elements.append(Spacer(1, 6 * mm))
        elements.append(Paragraph("Notes", heading_style))
        elements.append(Paragraph(invoice.notes, normal_style))

    # Bank details
    if settings.company_bank_details:
        elements.append(Spacer(1, 6 * mm))
        elements.append(Paragraph("Bank Details", heading_style))
        elements.append(Paragraph(settings.company_bank_details.replace("\n", "<br/>"), small_style))

    doc.build(elements)
    return output_path
