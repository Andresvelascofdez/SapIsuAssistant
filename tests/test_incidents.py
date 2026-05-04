"""Tests for SAP IS-U incidents and IP Box evidence support."""
import hashlib
from io import BytesIO

import pytest
from pypdf import PdfReader

from src.assistant.storage.kb_repository import KBItemRepository
from src.incidents.pdf.ipbox_dossier import generate_ipbox_dossier_pdf
from src.incidents.storage.incident_repository import IncidentRepository, compute_sha256
from src.shared.client_manager import ClientManager


def _make_api_client(tmp_path, monkeypatch, clients=("TST",), active_client="TST"):
    monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
    import src.web.dependencies as deps

    monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)
    cm = ClientManager(tmp_path)
    for code in clients:
        cm.register_client(code, f"{code} Client")

    from src.web.app import app
    from starlette.testclient import TestClient

    client = TestClient(app)
    if active_client:
        client.post("/api/session/client", json={"code": active_client})
    return client


def _pdf_text(path_or_bytes) -> str:
    reader = PdfReader(path_or_bytes)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class TestIncidentRepository:
    def test_create_update_evidence_and_summary(self, tmp_path):
        repo = IncidentRepository(tmp_path / "incidents.sqlite")
        incident = repo.create_incident(
            client_code="tst",
            title="Device register mismatch",
            period_year=2026,
            period_month=4,
            hours_spent=6.5,
            sap_module="IS-U",
            sap_process="Device Management",
            sap_objects=["EGERH", "EVER"],
            affected_ids="POD-1, DOC-9",
            problem_statement="Device history was inconsistent after move-in.",
            ipbox_relevance="QUALIFYING_CANDIDATE",
        )

        assert incident.client_code == "TST"
        assert incident.incident_code == "INC-2026-0001"
        assert repo.year_summary(2026)["total_hours"] == 6.5

        updated = repo.update_incident(
            incident.id,
            status="RESOLVED",
            hours_spent=7.25,
            solution="Adjusted validation and regenerated device links.",
        )
        assert updated.status == "RESOLVED"
        assert updated.hours_spent == 7.25

        payload = b"sap isu evidence"
        evidence = repo.add_evidence(
            incident_id=incident.id,
            title="Trace log",
            kind="FILE",
            storage_path="clients/TST/incident_evidence/file.txt",
            sha256=compute_sha256(payload),
            original_file_name="file.txt",
            size_bytes=len(payload),
        )
        assert evidence.sha256 == hashlib.sha256(payload).hexdigest()
        assert len(repo.list_evidence(incident.id)) == 1

    def test_validation_errors(self, tmp_path):
        repo = IncidentRepository(tmp_path / "incidents.sqlite")
        with pytest.raises(ValueError, match="Title"):
            repo.create_incident(client_code="TST", title="")
        with pytest.raises(ValueError, match="period_month"):
            repo.create_incident(client_code="TST", title="Bad month", period_month=13)
        with pytest.raises(ValueError, match="negative"):
            repo.create_incident(client_code="TST", title="Bad hours", hours_spent=-1)

    def test_client_database_isolation(self, tmp_path):
        repo_a = IncidentRepository(tmp_path / "clients" / "A" / "incidents.sqlite")
        repo_b = IncidentRepository(tmp_path / "clients" / "B" / "incidents.sqlite")

        inc_a = repo_a.create_incident(client_code="A", title="A incident", period_year=2026)
        inc_b = repo_b.create_incident(client_code="B", title="B incident", period_year=2026)

        assert [i.id for i in repo_a.list_incidents()] == [inc_a.id]
        assert [i.id for i in repo_b.list_incidents()] == [inc_b.id]
        assert repo_a.db_path != repo_b.db_path

    def test_client_manager_creates_incident_layout(self, tmp_path):
        cm = ClientManager(tmp_path)
        cm.register_client("ABC", "ABC Client")
        client_dir = tmp_path / "clients" / "ABC"

        assert (client_dir / "incidents.sqlite").exists()
        assert (client_dir / "incident_evidence").is_dir()


class TestIncidentAPI:
    def test_pages_load(self, tmp_path, monkeypatch):
        client = _make_api_client(tmp_path, monkeypatch)
        incident = client.post(
            "/api/incidents",
            json={"client_code": "TST", "title": "Page load incident", "period_year": 2026},
        ).json()

        incidents_page = client.get("/incidents")
        assert incidents_page.status_code == 200
        assert "startCreateIncident()" in incidents_page.text
        assert ':disabled="!activeClient"' not in incidents_page.text
        assert "Buscar" in incidents_page.text
        assert "Limpiar" in incidents_page.text
        assert client.get(f"/incidents/{incident['id']}?client_code=TST").status_code == 200
        assert client.get("/ipbox/dossier").status_code == 200

    def test_no_client_selected_rejected(self, tmp_path, monkeypatch):
        client = _make_api_client(tmp_path, monkeypatch, clients=("TST",), active_client=None)

        resp = client.get("/api/incidents")
        assert resp.status_code == 400
        assert "client" in resp.json()["error"].lower()

        resp = client.post("/api/incidents", json={"title": "Missing client"})
        assert resp.status_code == 400

    def test_create_list_filter_and_update(self, tmp_path, monkeypatch):
        client = _make_api_client(tmp_path, monkeypatch, clients=("TST", "ACME"), active_client="TST")

        resp = client.post(
            "/api/incidents",
            json={
                "client_code": "TST",
                "title": "Billing exception in invoicing",
                "status": "OPEN",
                "priority": "HIGH",
                "period_year": 2026,
                "period_month": 3,
                "hours_spent": 4.0,
                "sap_module": "IS-U",
                "sap_process": "Billing",
                "sap_objects": ["EA00", "ERCH"],
                "ipbox_relevance": "QUALIFYING_CANDIDATE",
            },
        )
        assert resp.status_code == 200
        incident_id = resp.json()["id"]

        client.post(
            "/api/incidents",
            json={
                "client_code": "ACME",
                "title": "Other client incident",
                "period_year": 2026,
            },
        )

        list_resp = client.get("/api/incidents?client_code=TST&year=2026&ipbox_relevance=QUALIFYING_CANDIDATE")
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["count"] == 1
        assert data["incidents"][0]["id"] == incident_id

        acme_resp = client.get("/api/incidents?client_code=ACME&year=2026")
        assert acme_resp.status_code == 200
        assert acme_resp.json()["incidents"][0]["client_code"] == "ACME"

        update_resp = client.put(
            f"/api/incidents/{incident_id}",
            json={"client_code": "TST", "status": "RESOLVED", "outcome": "Invoice simulation is stable."},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "RESOLVED"

        bad_resp = client.put(
            f"/api/incidents/{incident_id}",
            json={"client_code": "TST", "period_month": 99},
        )
        assert bad_resp.status_code == 400

    def test_search_covers_sap_objects_affected_ids_and_narrative_fields(self, tmp_path, monkeypatch):
        client = _make_api_client(tmp_path, monkeypatch)
        incident = client.post(
            "/api/incidents",
            json={
                "client_code": "TST",
                "title": "Search coverage incident",
                "period_year": 2026,
                "sap_objects": ["EGERH"],
                "affected_ids": ["POD-SEARCH-123"],
                "solution": "Use a deterministic rollover checklist.",
            },
        ).json()

        for term in ["EGERH", "POD-SEARCH-123", "rollover checklist"]:
            resp = client.get("/api/incidents", params={"client_code": "TST", "search": term})
            assert resp.status_code == 200
            assert any(row["id"] == incident["id"] for row in resp.json()["incidents"])

    def test_incident_with_knowledge_material_auto_creates_kb_draft(self, tmp_path, monkeypatch):
        client = _make_api_client(tmp_path, monkeypatch)

        resp = client.post(
            "/api/incidents",
            json={
                "client_code": "TST",
                "title": "Automatic draft incident",
                "period_year": 2026,
                "problem_statement": "A reusable IS-U validation failed.",
                "sap_objects": ["EVER"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        kb_id = data["auto_kb_draft_id"]

        kb_repo = KBItemRepository(tmp_path / "clients" / "TST" / "assistant_kb.sqlite")
        kb_item = kb_repo.get_by_id(kb_id)
        assert kb_item is not None
        assert kb_item.status == "DRAFT"
        assert "Automatic draft incident" in kb_item.title

        detail = client.get(f"/api/incidents/{data['id']}?client_code=TST").json()
        assert kb_id in detail["linked_kb_ids"]

    def test_update_incident_with_solution_auto_creates_kb_draft(self, tmp_path, monkeypatch):
        client = _make_api_client(tmp_path, monkeypatch)
        incident = client.post(
            "/api/incidents",
            json={"client_code": "TST", "title": "Draft on update", "period_year": 2026},
        ).json()
        assert "auto_kb_draft_id" not in incident

        resp = client.put(
            f"/api/incidents/{incident['id']}",
            json={
                "client_code": "TST",
                "status": "RESOLVED",
                "solution": "Captured a reusable resolution path.",
            },
        )
        assert resp.status_code == 200
        kb_id = resp.json()["auto_kb_draft_id"]

        kb_repo = KBItemRepository(tmp_path / "clients" / "TST" / "assistant_kb.sqlite")
        kb_item = kb_repo.get_by_id(kb_id)
        assert kb_item is not None
        assert kb_item.status == "DRAFT"

    def test_evidence_upload_link_and_delete(self, tmp_path, monkeypatch):
        client = _make_api_client(tmp_path, monkeypatch)
        incident_id = client.post(
            "/api/incidents",
            json={"client_code": "TST", "title": "Evidence incident", "period_year": 2026},
        ).json()["id"]

        upload_resp = client.post(
            f"/api/incidents/{incident_id}/evidence",
            data={"client_code": "TST", "kind": "FILE", "title": "Debug log"},
            files={"file": ("debug.txt", b"debug evidence", "text/plain")},
        )
        assert upload_resp.status_code == 200
        file_ev = upload_resp.json()
        assert file_ev["sha256"] == hashlib.sha256(b"debug evidence").hexdigest()
        assert (tmp_path / file_ev["storage_path"]).exists()

        link_resp = client.post(
            f"/api/incidents/{incident_id}/evidence",
            data={
                "client_code": "TST",
                "kind": "LINK",
                "title": "Jira ticket",
                "url": "https://example.invalid/ISSUE-1",
            },
        )
        assert link_resp.status_code == 200
        assert link_resp.json()["kind"] == "LINK"

        detail_resp = client.get(f"/api/incidents/{incident_id}?client_code=TST")
        assert detail_resp.status_code == 200
        assert len(detail_resp.json()["evidence"]) == 2

        delete_resp = client.delete(
            f"/api/incidents/{incident_id}/evidence/{file_ev['id']}?client_code=TST"
        )
        assert delete_resp.status_code == 200
        assert not (tmp_path / file_ev["storage_path"]).exists()

    def test_generate_kb_draft_creates_draft_and_links_incident(self, tmp_path, monkeypatch):
        client = _make_api_client(tmp_path, monkeypatch)
        incident = client.post(
            "/api/incidents",
            json={
                "client_code": "TST",
                "title": "Move-in validation enhancement",
                "status": "RESOLVED",
                "period_year": 2026,
                "period_month": 5,
                "sap_process": "Move-in",
                "sap_objects": ["EVER", "EANL"],
                "problem_statement": "Move-in failed for edge case PODs.",
                "solution": "Added a reusable validation path.",
            },
        ).json()

        resp = client.post(
            f"/api/incidents/{incident['id']}/generate-kb-draft",
            json={"client_code": "TST"},
        )
        assert resp.status_code == 200
        kb_id = resp.json()["kb_id"]

        kb_repo = KBItemRepository(tmp_path / "clients" / "TST" / "assistant_kb.sqlite")
        kb_item = kb_repo.get_by_id(kb_id)
        assert kb_item is not None
        assert kb_item.status == "DRAFT"
        assert kb_item.client_scope == "client"

        detail = client.get(f"/api/incidents/{incident['id']}?client_code=TST").json()
        assert kb_id in detail["linked_kb_ids"]

    def test_dossier_api_returns_pdf_with_english_sections(self, tmp_path, monkeypatch):
        client = _make_api_client(tmp_path, monkeypatch, clients=("TST", "ACME"), active_client="TST")
        client.post(
            "/api/incidents",
            json={
                "client_code": "TST",
                "title": "Dossier candidate",
                "period_year": 2026,
                "hours_spent": 8,
                "sap_process": "Meter Reading",
                "technical_uncertainty": "Unexpected register estimation path.",
                "solution": "Built deterministic validation.",
                "verification": "Regression checks passed.",
                "outcome": "Reusable evidence pattern created.",
                "ipbox_relevance": "QUALIFYING_CANDIDATE",
            },
        )
        client.post(
            "/api/incidents",
            json={
                "client_code": "ACME",
                "title": "Operational non-candidate",
                "period_year": 2026,
                "hours_spent": 2,
                "ipbox_relevance": "NOT_QUALIFYING",
            },
        )

        resp = client.get("/api/ipbox/dossier?year=2026")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        text = _pdf_text(BytesIO(resp.content))
        assert "Annual IP Box Evidence Dossier 2026" in text
        assert "Methodology Note" in text
        assert "Totals by Client" in text
        assert "Qualifying Candidate Appendices" in text
        assert "Dossier candidate" in text


class TestIpBoxPdf:
    def test_pdf_contains_totals_incident_details_and_evidence_hash(self, tmp_path):
        repo = IncidentRepository(tmp_path / "incidents.sqlite")
        incident = repo.create_incident(
            client_code="TST",
            title="Reusable billing simulation",
            period_year=2026,
            period_month=2,
            hours_spent=5.5,
            sap_process="Billing",
            sap_objects=["ERCH", "EA00"],
            problem_statement="Billing simulation did not handle a new tariff condition.",
            technical_uncertainty="The failing path was not documented in standard customizing.",
            investigation="Compared billing document traces and custom validation rules.",
            solution="Implemented a reusable simulation guard.",
            verification="Replayed affected PODs and verified invoice output.",
            outcome="Reduced manual billing correction effort.",
            ipbox_relevance="QUALIFYING_CANDIDATE",
        )
        evidence = repo.add_evidence(
            incident.id,
            title="Trace extract",
            kind="LINK",
            url="https://example.invalid/trace",
            sha256="a" * 64,
        )

        out_path = generate_ipbox_dossier_pdf(
            2026,
            [(incident, [evidence])],
            tmp_path / "dossier.pdf",
        )
        text = _pdf_text(str(out_path))

        assert "Annual IP Box Evidence Dossier 2026" in text
        assert "Total Hours" in text
        assert "Billing" in text
        assert "Technical Uncertainty" in text
        assert "a" * 64 in text.replace("\n", "")
