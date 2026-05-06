"""Monthly IP Box evidence reporting helpers."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from src.ipbox.usage_logging import export_usage_events_csv, read_usage_events


REVENUE_MAPPING_COLUMNS = [
    "month",
    "invoice_reference",
    "client",
    "service_description",
    "invoice_amount",
    "total_hours",
    "productive_sap_isu_hours",
    "tool_assisted_hours",
    "assisted_hours_percentage",
    "software_contribution_factor",
    "qualifying_service_factor",
    "proposed_ip_attribution_percentage",
    "proposed_ip_income_amount",
    "excluded_amount",
    "notes",
]


@dataclass
class MonthlyIPBoxSummary:
    month: str
    usage_count: int
    assisted_usage_count: int
    client_delivery_usage_count: int
    actual_hours: float
    assisted_hours: float
    estimated_without_tool_hours: float
    estimated_time_saved_hours: float
    average_software_contribution_factor: float
    qualifying_service_factor: float
    proposed_ip_attribution_percentage: float
    total_relevant_sap_isu_service_revenue: float
    excluded_revenue: float
    proposed_ip_income_amount: float


def calculate_ip_attribution(
    productive_hours_assisted: float,
    total_productive_sap_isu_hours: float,
    software_contribution_factor: float,
    qualifying_service_factor: float,
) -> float:
    if total_productive_sap_isu_hours <= 0:
        return 0.0
    assisted_ratio = productive_hours_assisted / total_productive_sap_isu_hours
    value = assisted_ratio * software_contribution_factor * qualifying_service_factor
    return round(max(0.0, min(value, 1.0)) * 100, 2)


def aggregate_monthly_usage(
    events: list[dict],
    *,
    month: str,
    total_relevant_sap_isu_service_revenue: float = 0.0,
    excluded_revenue: float = 0.0,
    total_productive_sap_isu_hours: float | None = None,
    qualifying_service_factor: float = 1.0,
) -> MonthlyIPBoxSummary:
    month_events = [event for event in events if str(event.get("timestamp", "")).startswith(month)]
    actual_minutes = sum(float(event.get("actual_time_minutes") or 0) for event in month_events)
    assisted_minutes = sum(
        float(event.get("actual_time_minutes") or 0)
        for event in month_events
        if event.get("output_used") in {"YES", "PARTIAL"} or event.get("used_for_client_delivery") == "YES"
    )
    without_tool_minutes = sum(float(event.get("estimated_time_without_tool_minutes") or 0) for event in month_events)
    saved_minutes = sum(float(event.get("estimated_time_saved_minutes") or 0) for event in month_events)
    contribution_values = [
        float(event.get("software_contribution_factor") or 0)
        for event in month_events
        if float(event.get("software_contribution_factor") or 0) > 0
    ]
    avg_contribution = round(mean(contribution_values), 4) if contribution_values else 0.0
    total_hours = total_productive_sap_isu_hours if total_productive_sap_isu_hours is not None else actual_minutes / 60
    attribution = calculate_ip_attribution(
        assisted_minutes / 60,
        total_hours,
        avg_contribution,
        qualifying_service_factor,
    )
    ip_income = round(total_relevant_sap_isu_service_revenue * attribution / 100, 2)
    return MonthlyIPBoxSummary(
        month=month,
        usage_count=len(month_events),
        assisted_usage_count=sum(1 for event in month_events if event.get("output_used") in {"YES", "PARTIAL"}),
        client_delivery_usage_count=sum(1 for event in month_events if event.get("used_for_client_delivery") == "YES"),
        actual_hours=round(actual_minutes / 60, 2),
        assisted_hours=round(assisted_minutes / 60, 2),
        estimated_without_tool_hours=round(without_tool_minutes / 60, 2),
        estimated_time_saved_hours=round(saved_minutes / 60, 2),
        average_software_contribution_factor=avg_contribution,
        qualifying_service_factor=qualifying_service_factor,
        proposed_ip_attribution_percentage=attribution,
        total_relevant_sap_isu_service_revenue=total_relevant_sap_isu_service_revenue,
        excluded_revenue=excluded_revenue,
        proposed_ip_income_amount=ip_income,
    )


def generate_monthly_ip_report(
    data_root: Path,
    reports_root: Path,
    month: str,
    *,
    total_relevant_sap_isu_service_revenue: float = 0.0,
    excluded_revenue: float = 0.0,
    total_productive_sap_isu_hours: float | None = None,
    qualifying_service_factor: float = 1.0,
) -> tuple[MonthlyIPBoxSummary, Path, Path]:
    events = read_usage_events(data_root, month)
    summary = aggregate_monthly_usage(
        events,
        month=month,
        total_relevant_sap_isu_service_revenue=total_relevant_sap_isu_service_revenue,
        excluded_revenue=excluded_revenue,
        total_productive_sap_isu_hours=total_productive_sap_isu_hours,
        qualifying_service_factor=qualifying_service_factor,
    )
    output_dir = Path(reports_root) / "ip_box" / month
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "monthly_ip_usage_report.md"
    csv_path = output_dir / "usage_events.csv"
    md_path.write_text(_render_monthly_markdown(summary), encoding="utf-8")
    export_usage_events_csv(events, csv_path)
    return summary, md_path, csv_path


def write_revenue_mapping_template(output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(REVENUE_MAPPING_COLUMNS)
    return output_path


def _render_monthly_markdown(summary: MonthlyIPBoxSummary) -> str:
    return f"""# Monthly IP Box Usage Report - {summary.month}

This report is an internal evidence artefact for advisor review. It does not determine final Cyprus IP Box eligibility, nexus fraction, qualifying profit or tax treatment.

| Metric | Value |
| --- | ---: |
| Usage records | {summary.usage_count} |
| Assisted usage records | {summary.assisted_usage_count} |
| Used for client delivery | {summary.client_delivery_usage_count} |
| Actual productive hours recorded | {summary.actual_hours:.2f} |
| Tool-assisted hours | {summary.assisted_hours:.2f} |
| Estimated hours without tool | {summary.estimated_without_tool_hours:.2f} |
| Estimated time saved | {summary.estimated_time_saved_hours:.2f} |
| Average software contribution factor | {summary.average_software_contribution_factor:.2f} |
| Qualifying service factor | {summary.qualifying_service_factor:.2f} |
| Proposed IP attribution percentage | {summary.proposed_ip_attribution_percentage:.2f}% |
| Relevant SAP IS-U service revenue | {summary.total_relevant_sap_isu_service_revenue:.2f} |
| Excluded revenue | {summary.excluded_revenue:.2f} |
| Proposed IP income amount | {summary.proposed_ip_income_amount:.2f} |

## Formula

IP Attribution % = (Productive Hours Assisted by SAP IS-U Assistant / Total Productive SAP IS-U Hours) x Software Contribution Factor x Qualifying Service Factor.

## Advisor Review

The proposed percentage is a management estimate based on recorded usage. It must be reviewed by qualified Cyprus tax advisors before being used in any filing or tax position.
"""
