from pathlib import Path

from src.ipbox.reporting import (
    calculate_ip_attribution,
    generate_monthly_ip_report,
    write_revenue_mapping_template,
)
from src.ipbox.usage_logging import (
    create_usage_record,
    detect_custom_sap_objects,
    generate_usage_id,
    hash_text,
    list_usage_events,
    read_usage_events,
    save_usage_event,
    update_usage_event,
)
from src.shared.client_manager import ClientManager


def test_usage_id_generation_is_stable_shape():
    usage_id = generate_usage_id()

    assert usage_id.startswith("USE-")
    assert len(usage_id.split("-")) == 3


def test_usage_log_save_and_read_preserves_namespace_fields(tmp_path):
    record = create_usage_record(
        user="consultant",
        active_client="CLIENT_A",
        ticket_reference="TCK000001",
        task_type="incident_analysis",
        sap_module="IS-U",
        sap_isu_process="meter-reading",
        search_mode="COMBINED",
        sources_used="BOTH",
        query_text="How to troubleshoot EABL validation?",
        response_text="Check EABL, EL31 and validation messages.",
        number_of_documents_retrieved=3,
        contains_z_objects=True,
        namespace_applied="CLIENT_A",
        output_used="YES",
        used_for_client_delivery="YES",
        human_reviewed="YES",
        verification_status="CONSULTANT_VERIFIED",
        software_features_used="CHAT_RAG;KB_RETRIEVAL",
        retrieved_kb_item_ids="KB-001;KB-002",
        output_reference="JIRA-123 comment 4",
        actual_time_minutes=45,
        estimated_time_without_tool_minutes=90,
        estimated_time_saved_minutes=45,
        software_contribution_factor=0.7,
        timestamp="2026-05-06T10:00:00+00:00",
    )

    path = save_usage_event(tmp_path, record)
    events = read_usage_events(tmp_path, "2026-05")

    assert path == tmp_path / "ip_box" / "usage_logs" / "2026-05.jsonl"
    assert len(events) == 1
    assert events[0]["active_client"] == "CLIENT_A"
    assert events[0]["namespace_applied"] == "CLIENT_A"
    assert events[0]["human_reviewed"] == "YES"
    assert events[0]["software_features_used"] == "CHAT_RAG;KB_RETRIEVAL"
    assert events[0]["output_reference"] == "JIRA-123 comment 4"
    assert events[0]["query_hash"] == hash_text("How to troubleshoot EABL validation?")
    assert events[0]["product_version"]
    assert events[0]["retrieval_count"] == 3
    assert events[0]["manual_verification_status"] == "TODO/TBC"


def test_usage_log_review_update_preserves_extra_audit_fields(tmp_path):
    record = create_usage_record(
        user="consultant",
        active_client="CLIENT_A",
        ticket_reference="TCK000003",
        task_type="RAG_CHAT",
        sap_module="IS-U",
        sap_isu_process="billing",
        search_mode="AI_ONLY",
        sources_used="KNOWLEDGE_BASE",
        timestamp="2026-05-12T12:00:00+00:00",
        extra={"chat_session_id": "CHAT-001"},
    )
    save_usage_event(tmp_path, record.to_dict())

    updated = update_usage_event(
        tmp_path,
        record.usage_id,
        {
            "manual_verification_status": "used",
            "output_used": "YES",
            "used_for_client_delivery": "YES",
            "human_reviewed": "YES",
            "estimated_time_without_tool_minutes": "90",
            "actual_time_minutes": "30",
            "estimated_time_saved_minutes": "60",
            "notes": "Reviewed against anonymised delivery evidence.",
        },
    )

    assert updated is not None
    events = read_usage_events(tmp_path, "2026-05")
    assert events[0]["manual_verification_status"] == "used"
    assert events[0]["chat_session_id"] == "CHAT-001"
    assert events[0]["estimated_time_saved_minutes"] == 60


def test_usage_event_filters_and_custom_object_detection(tmp_path):
    save_usage_event(
        tmp_path,
        create_usage_record(
            user="consultant",
            active_client="CLIENT_A",
            ticket_reference="TCK000004",
            task_type="RAG_CHAT",
            sap_module="IS-U",
            sap_isu_process="meter-reading",
            search_mode="AI_ONLY",
            sources_used="KNOWLEDGE_BASE",
            output_used="YES",
            used_for_client_delivery="YES",
            namespace_applied="CLIENT:CLIENT_A",
            standard_kb_used="YES",
            client_kb_used="YES",
            timestamp="2026-05-13T12:00:00+00:00",
        ),
    )
    save_usage_event(
        tmp_path,
        create_usage_record(
            user="consultant",
            active_client="CLIENT_B",
            ticket_reference="TCK000005",
            task_type="RAG_CHAT",
            sap_module="FI-CA",
            sap_isu_process="payments",
            search_mode="AI_ONLY",
            sources_used="KNOWLEDGE_BASE",
            excluded_from_ip_evidence="YES",
            timestamp="2026-05-13T13:00:00+00:00",
        ),
    )

    events = list_usage_events(
        tmp_path,
        month="2026-05",
        client="CLIENT_A",
        sap_process="meter-reading",
        output_used="YES",
        delivery_used="YES",
        include_excluded=False,
    )

    assert len(events) == 1
    assert events[0]["active_client"] == "CLIENT_A"
    assert detect_custom_sap_objects(["ZMR_VALIDATION"]) is True
    assert detect_custom_sap_objects(["YBILLING_EXIT"]) is True
    assert detect_custom_sap_objects(["/CLIENT/UTIL_CLASS"]) is True
    assert detect_custom_sap_objects(["EABL", "ERCH"]) is False


def test_monthly_aggregation_and_report_generation(tmp_path):
    save_usage_event(
        tmp_path,
        create_usage_record(
            user="consultant",
            active_client="CLIENT_A",
            ticket_reference="TCK000002",
            task_type="jira_response",
            sap_module="IS-U",
            sap_isu_process="billing",
            search_mode="AI_ONLY",
            sources_used="KNOWLEDGE_BASE",
            output_used="YES",
            used_for_client_delivery="YES",
            actual_time_minutes=60,
            estimated_time_without_tool_minutes=120,
            estimated_time_saved_minutes=60,
            software_contribution_factor=0.7,
            timestamp="2026-05-10T12:00:00+00:00",
        ),
    )
    save_usage_event(
        tmp_path,
        create_usage_record(
            user="consultant",
            active_client="CLIENT_A",
            ticket_reference="ADMIN-EXCLUDED",
            task_type="ADMIN",
            sap_module="",
            sap_isu_process="",
            search_mode="AI_ONLY",
            sources_used="MANUAL_CONTEXT",
            output_used="YES",
            used_for_client_delivery="YES",
            actual_time_minutes=120,
            estimated_time_without_tool_minutes=120,
            estimated_time_saved_minutes=0,
            software_contribution_factor=1.0,
            excluded_from_ip_evidence="YES",
            timestamp="2026-05-10T13:00:00+00:00",
        ),
    )

    summary, md_path, csv_path = generate_monthly_ip_report(
        tmp_path,
        tmp_path / "reports",
        "2026-05",
        total_relevant_sap_isu_service_revenue=10_000,
        total_productive_sap_isu_hours=1,
        qualifying_service_factor=0.98,
    )

    assert summary.usage_count == 2
    assert summary.proposed_ip_attribution_percentage == 68.6
    assert summary.proposed_ip_income_amount == 6860
    assert summary.total_productive_sap_isu_hours == 1
    assert summary.assisted_hours_percentage == 100
    assert summary.assisted_hours == 1
    assert md_path.exists()
    assert csv_path.exists()
    assert "Monthly IP Box Usage Report" in md_path.read_text(encoding="utf-8")
    assert "Missing Fields / TODOs" in md_path.read_text(encoding="utf-8")


def test_ip_attribution_formula_handles_zero_hours():
    assert calculate_ip_attribution(10, 0, 0.7, 0.98) == 0.0
    assert calculate_ip_attribution(88, 100, 0.7, 0.98) == 60.37


def test_revenue_mapping_template_generation(tmp_path):
    output = write_revenue_mapping_template(tmp_path / "revenue_mapping_template.csv")
    header = output.read_text(encoding="utf-8").splitlines()[0]

    assert "invoice_reference" in header
    assert "software_assisted_hours" in header
    assert "advisor_notes" in header
    assert "proposed_ip_income_amount" in header


def test_ipbox_usage_review_api_and_report_export(tmp_path, monkeypatch):
    monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
    import src.web.dependencies as deps

    monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)
    ClientManager(tmp_path).register_client("CLIENT_A", "Client A")

    record = create_usage_record(
        user="consultant",
        active_client="CLIENT_A",
        ticket_reference="TCK000006",
        task_type="RAG_CHAT",
        sap_module="IS-U",
        sap_isu_process="Device Management",
        search_mode="AI_ONLY",
        sources_used="KNOWLEDGE_BASE",
        timestamp="2026-05-15T09:00:00+00:00",
    )
    save_usage_event(tmp_path, record)

    from src.web.app import app
    from starlette.testclient import TestClient

    client = TestClient(app)
    assert client.get("/ipbox/usage").status_code == 200

    list_resp = client.get("/api/ipbox/usage-events?month=2026-05&client=CLIENT_A")
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] == 1

    update_resp = client.put(
        f"/api/ipbox/usage-events/{record.usage_id}",
        json={
            "manual_verification_status": "reviewed",
            "human_reviewed": "YES",
            "ticket_reference": "TCK000006-REVIEWED",
            "sap_process": "Device Management",
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["manual_verification_status"] == "reviewed"
    assert update_resp.json()["sap_isu_process"] == "Device Management"

    report_resp = client.post("/api/ipbox/monthly-report", json={"month": "2026-05"})
    assert report_resp.status_code == 200
    assert (tmp_path.parent / "reports" / "ip_box" / "2026-05" / "monthly_ip_usage_report.md").exists()
