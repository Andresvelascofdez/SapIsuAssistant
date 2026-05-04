"""Annual IP Box evidence dossier PDF generation."""
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from src.incidents.storage.incident_repository import Incident, IncidentEvidence


def _safe(value: object) -> str:
    if value is None:
        return ""
    return escape(str(value))


def _json_items(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(v) for v in data if str(v).strip()]


def _p(text: object, style):
    return Paragraph(_safe(text), style)


def _section(title: str, value: str | None, styles: dict) -> list:
    if not value:
        return []
    return [
        Paragraph(_safe(title), styles["section"]),
        Paragraph(_safe(value).replace("\n", "<br/>"), styles["body"]),
        Spacer(1, 3 * mm),
    ]


def generate_ipbox_dossier_pdf(
    year: int,
    incidents_with_evidence: list[tuple[Incident, list[IncidentEvidence]]],
    output_path: Path,
) -> Path:
    """Generate an annual English PDF evidence dossier."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "DossierTitle", parent=base["Title"], fontSize=22, spaceAfter=8 * mm
        ),
        "h2": ParagraphStyle(
            "DossierH2", parent=base["Heading2"], fontSize=14, spaceBefore=5 * mm, spaceAfter=3 * mm
        ),
        "section": ParagraphStyle(
            "DossierSection", parent=base["Heading3"], fontSize=10, spaceBefore=3 * mm, spaceAfter=1 * mm
        ),
        "body": ParagraphStyle(
            "DossierBody", parent=base["BodyText"], fontSize=8, leading=10
        ),
        "small": ParagraphStyle(
            "DossierSmall", parent=base["BodyText"], fontSize=7, leading=9
        ),
    }

    incidents = [item[0] for item in incidents_with_evidence]
    total_hours = round(sum(i.hours_spent for i in incidents), 2)
    qualifying = [i for i in incidents if i.ipbox_relevance == "QUALIFYING_CANDIDATE"]

    by_client: dict[str, dict] = defaultdict(lambda: {"count": 0, "hours": 0.0})
    by_process: dict[str, dict] = defaultdict(lambda: {"count": 0, "hours": 0.0})
    for incident in incidents:
        by_client[incident.client_code]["count"] += 1
        by_client[incident.client_code]["hours"] += incident.hours_spent
        process_key = incident.sap_process or incident.sap_module or "Unspecified"
        by_process[process_key]["count"] += 1
        by_process[process_key]["hours"] += incident.hours_spent

    elements = []
    elements.append(Paragraph(f"SAP IS-U Incident Assistant - Annual IP Box Evidence Dossier {year}", styles["title"]))
    elements.append(_p(f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}", styles["body"]))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph("Methodology Note", styles["h2"]))
    elements.append(
        _p(
            "This dossier summarizes SAP IS-U software support and development incidents recorded in the tool. "
            "It is intended as an evidence pack for advisor review under the Cyprus IP Box regime. "
            "It documents technical problems, uncertainty, investigation, implementation, verification, evidence, "
            "and hours. It does not calculate qualifying expenditure, overall expenditure, nexus fraction, "
            "tax savings, or final eligibility.",
            styles["body"],
        )
    )
    elements.append(Spacer(1, 5 * mm))

    summary_data = [
        ["Year", "Incidents", "Qualifying Candidates", "Total Hours"],
        [str(year), str(len(incidents)), str(len(qualifying)), f"{total_hours:.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[35 * mm, 35 * mm, 50 * mm, 35 * mm])
    summary_table.setStyle(_table_style())
    elements.append(summary_table)

    elements.append(Paragraph("Totals by Client", styles["h2"]))
    client_rows = [["Client", "Incidents", "Hours"]]
    for client, data in sorted(by_client.items()):
        client_rows.append([client, str(data["count"]), f"{data['hours']:.2f}"])
    elements.append(Table(client_rows, colWidths=[45 * mm, 35 * mm, 35 * mm], style=_table_style()))

    elements.append(Paragraph("Totals by SAP Process or Module", styles["h2"]))
    process_rows = [["SAP Process / Module", "Incidents", "Hours"]]
    for process, data in sorted(by_process.items()):
        process_rows.append([_p(process, styles["small"]), str(data["count"]), f"{data['hours']:.2f}"])
    elements.append(Table(process_rows, colWidths=[90 * mm, 35 * mm, 35 * mm], style=_table_style()))

    elements.append(Paragraph("Incident Register", styles["h2"]))
    table_rows = [["ID", "Client", "Title", "Status", "IP Box", "Hours", "SAP Objects", "Outcome"]]
    for incident in incidents:
        table_rows.append(
            [
                incident.incident_code,
                incident.client_code,
                _p(incident.title, styles["small"]),
                incident.status,
                incident.ipbox_relevance,
                f"{incident.hours_spent:.2f}",
                _p(", ".join(_json_items(incident.sap_objects_json)), styles["small"]),
                _p(incident.outcome or "", styles["small"]),
            ]
        )
    table = Table(
        table_rows,
        colWidths=[25 * mm, 22 * mm, 55 * mm, 25 * mm, 42 * mm, 20 * mm, 50 * mm, 65 * mm],
        repeatRows=1,
    )
    table.setStyle(_table_style(font_size=7))
    elements.append(table)

    if qualifying:
        elements.append(PageBreak())
        elements.append(Paragraph("Qualifying Candidate Appendices", styles["h2"]))
        evidence_map = {incident.id: evidence for incident, evidence in incidents_with_evidence}
        for idx, incident in enumerate(qualifying, 1):
            if idx > 1:
                elements.append(PageBreak())
            elements.append(Paragraph(f"{incident.incident_code} - {escape(incident.title)}", styles["h2"]))
            meta = (
                f"Client: {incident.client_code} | Period: {incident.period_year}-{incident.period_month:02d} | "
                f"Status: {incident.status} | Hours: {incident.hours_spent:.2f} | "
                f"SAP Process: {incident.sap_process or 'N/A'} | SAP Module: {incident.sap_module or 'N/A'}"
            )
            elements.append(_p(meta, styles["body"]))
            elements.extend(_section("Problem Statement", incident.problem_statement, styles))
            elements.extend(_section("Technical Uncertainty", incident.technical_uncertainty, styles))
            elements.extend(_section("Investigation", incident.investigation, styles))
            elements.extend(_section("Solution", incident.solution, styles))
            elements.extend(_section("Implementation Notes", incident.implementation_notes, styles))
            elements.extend(_section("Verification", incident.verification, styles))
            elements.extend(_section("Outcome", incident.outcome, styles))
            elements.extend(_section("Reusable Knowledge", incident.reusable_knowledge, styles))

            sap_objects = ", ".join(_json_items(incident.sap_objects_json)) or "N/A"
            affected_ids = ", ".join(_json_items(incident.affected_ids_json)) or "N/A"
            linked_kb = ", ".join(_json_items(incident.linked_kb_ids_json)) or "N/A"
            elements.append(_p(f"SAP Objects: {sap_objects}", styles["small"]))
            elements.append(_p(f"Affected IDs: {affected_ids}", styles["small"]))
            elements.append(_p(f"Linked KB Drafts: {linked_kb}", styles["small"]))
            elements.append(Spacer(1, 2 * mm))

            evidence = evidence_map.get(incident.id, [])
            evidence_rows = [["Title", "Kind", "Reference", "SHA256"]]
            for ev in evidence:
                ref = ev.url or ev.storage_path or ""
                evidence_rows.append(
                    [
                        _p(ev.title, styles["small"]),
                        ev.kind,
                        _p(ref, styles["small"]),
                        _p(ev.sha256 or "", styles["small"]),
                    ]
                )
            if len(evidence_rows) == 1:
                evidence_rows.append(["No evidence attached", "", "", ""])
            evidence_table = Table(
                evidence_rows,
                colWidths=[60 * mm, 22 * mm, 110 * mm, 90 * mm],
                repeatRows=1,
            )
            evidence_table.setStyle(_table_style(font_size=7))
            elements.append(evidence_table)

    doc.build(elements)
    return output_path


def _table_style(font_size: int = 8) -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edf9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]
    )
