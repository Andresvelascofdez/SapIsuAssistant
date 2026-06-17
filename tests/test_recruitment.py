"""Tests for the Recruitment candidate database module."""
from pathlib import Path

import pytest

from core.recruitment.candidate_manager import CandidateManager, CandidateValidationError
from core.recruitment.cv_autofill import autofill_from_text
from core.recruitment.cv_parser import import_cv


def _api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
    import src.web.dependencies as deps

    monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)
    from src.web.app import app
    from starlette.testclient import TestClient

    return TestClient(app)


class TestCandidateManager:
    def test_schema_and_folders_are_created(self, tmp_path):
        manager = CandidateManager(tmp_path)

        assert manager.db_path == tmp_path / "recruitment" / "candidates.db"
        assert manager.db_path.exists()
        assert manager.cvs_dir.is_dir()

    def test_create_get_update_delete_candidate(self, tmp_path):
        manager = CandidateManager(tmp_path)
        candidate = manager.create_candidate(
            {
                "full_name": "Jane Candidate",
                "email": "jane@example.test",
                "main_role": "SAP IS-U Consultant",
                "work_mode": "Remote",
                "currency": "EUR",
            }
        )

        assert candidate.id
        assert candidate.full_name == "Jane Candidate"
        assert candidate.work_mode == "Remote"
        assert candidate.currency == "EUR"

        updated = manager.update_candidate(
            candidate.id,
            {
                "phone": "+34 600 111 222",
                "skills": "Billing, device management",
                "rate_hour": "55,5",
            },
        )
        assert updated.phone == "+34 600 111 222"
        assert updated.skills == "Billing, device management"
        assert updated.rate_hour == 55.5

        assert manager.get_candidate(candidate.id).email == "jane@example.test"
        assert manager.delete_candidate(candidate.id) is True
        assert manager.get_candidate(candidate.id) is None
        assert manager.delete_candidate(candidate.id) is False

    def test_validation_requires_name_and_contact(self, tmp_path):
        manager = CandidateManager(tmp_path)

        with pytest.raises(CandidateValidationError, match="Full name"):
            manager.create_candidate({"email": "missing-name@example.test"})
        with pytest.raises(CandidateValidationError, match="Email or phone"):
            manager.create_candidate({"full_name": "No Contact"})
        with pytest.raises(CandidateValidationError, match="Work mode"):
            manager.create_candidate({"full_name": "Bad Mode", "email": "bad@example.test", "work_mode": "Freelance"})
        with pytest.raises(CandidateValidationError, match="Currency"):
            manager.create_candidate({"full_name": "Bad Currency", "email": "bad@example.test", "currency": "CHF"})
        with pytest.raises(CandidateValidationError, match="numeric"):
            manager.create_candidate({"full_name": "Bad Rate", "email": "bad@example.test", "rate_hour": "abc"})
        with pytest.raises(CandidateValidationError, match="negative"):
            manager.create_candidate({"full_name": "Bad Rate", "email": "bad@example.test", "rate_day": -1})

    def test_search_and_combined_filters(self, tmp_path):
        manager = CandidateManager(tmp_path)
        manager.create_candidate(
            {
                "full_name": "Jane Candidate",
                "email": "jane@example.test",
                "country": "Spain",
                "seniority": "Senior",
                "skills": "ABAP, debugging, invoicing",
                "sap_modules": "SAP IS-U Billing, FI-CA",
                "languages": "English, Spanish",
                "work_mode": "Remote",
                "rate_hour": 60,
                "rate_day": 480,
                "cv_text": "Deep EABL and meter reading background.",
            }
        )
        manager.create_candidate(
            {
                "full_name": "John Onsite",
                "phone": "+44 7000 000000",
                "country": "United Kingdom",
                "seniority": "Junior",
                "skills": "Testing",
                "sap_modules": "SAP MM",
                "languages": "English",
                "work_mode": "Onsite",
                "rate_hour": 35,
                "rate_day": 300,
            }
        )

        assert [c.full_name for c in manager.list_candidates(search="EABL")] == ["Jane Candidate"]
        filtered = manager.list_candidates(
            filters={
                "skill_text": "debug",
                "sap_module_text": "billing",
                "language_text": "spanish",
                "country": "spa",
                "seniority": "senior",
                "work_mode": "Remote",
                "max_hourly_rate": "70",
                "max_daily_rate": "500",
            }
        )
        assert [c.full_name for c in filtered] == ["Jane Candidate"]

        assert manager.list_candidates(filters={"max_hourly_rate": "not-a-number"})
        assert manager.list_candidates(filters={"max_hourly_rate": "40"})[0].full_name == "John Onsite"
        assert manager.search_candidates("onsite")[0].full_name == "John Onsite"

    def test_list_order_uses_latest_update_then_id(self, tmp_path):
        manager = CandidateManager(tmp_path)
        first = manager.create_candidate({"full_name": "First Candidate", "email": "first@example.test"})
        second = manager.create_candidate({"full_name": "Second Candidate", "email": "second@example.test"})

        assert [c.id for c in manager.list_candidates()] == [second.id, first.id]


class TestCvParserAndAutofill:
    def test_txt_import_copies_extracts_and_autofills_without_saving(self, tmp_path):
        source = tmp_path / "Jane Candidate CV.txt"
        source.write_text(
            "\n".join(
                [
                    "Jane Candidate",
                    "Senior SAP IS-U Consultant",
                    "jane@example.test | +34 600 111 222",
                    "https://www.linkedin.com/in/jane-candidate",
                    "Over 10 years of experience",
                    "Hourly rate 55 EUR",
                    "Daily rate 450 EUR",
                ]
            ),
            encoding="utf-8",
        )

        imported = import_cv(source, data_root=tmp_path)
        copied = Path(imported["cv_file_path"])
        assert copied.exists()
        assert copied.parent == tmp_path / "recruitment" / "cvs"
        assert "Jane Candidate" in imported["cv_text"]
        assert imported["error"] is None

        data = autofill_from_text(imported["cv_text"])
        assert data["full_name"] == "Jane Candidate"
        assert data["email"] == "jane@example.test"
        assert data["phone"] == "+34 600 111 222"
        assert "linkedin.com/in/jane-candidate" in data["linkedin"]
        assert data["main_role"] == "Senior SAP IS-U Consultant"
        assert data["seniority"] == "Senior"
        assert data["years_experience"] == "over 10 years"
        assert data["rate_hour"] == 55
        assert data["rate_day"] == 450
        assert data["currency"] == "EUR"
        assert "skills" not in data
        assert "sap_modules" not in data

    def test_docx_import_extracts_text(self, tmp_path):
        from docx import Document

        source = tmp_path / "cv.docx"
        document = Document()
        document.add_paragraph("Alex Profile")
        document.add_paragraph("Lead SAP IS-U Architect")
        document.save(source)

        imported = import_cv(source, data_root=tmp_path)

        assert imported["error"] is None
        assert "Alex Profile" in imported["cv_text"]
        assert "Lead SAP IS-U Architect" in imported["cv_text"]

    def test_pdf_import_extracts_text(self, tmp_path):
        from reportlab.pdfgen import canvas

        source = tmp_path / "cv.pdf"
        pdf = canvas.Canvas(str(source))
        pdf.drawString(72, 720, "PDF Candidate")
        pdf.drawString(72, 700, "SAP IS-U Billing Consultant")
        pdf.save()

        imported = import_cv(source, data_root=tmp_path)

        assert imported["error"] is None
        assert "PDF Candidate" in imported["cv_text"]
        assert "SAP IS-U Billing Consultant" in imported["cv_text"]

    def test_broken_pdf_is_stored_with_friendly_extraction_error(self, tmp_path):
        source = tmp_path / "broken.pdf"
        source.write_bytes(b"not a real pdf")

        imported = import_cv(source, data_root=tmp_path)

        assert Path(imported["cv_file_path"]).exists()
        assert imported["cv_text"] == ""
        assert "text extraction failed" in imported["error"]


class TestRecruitmentApi:
    def test_page_contains_required_controls(self, tmp_path, monkeypatch):
        client = _api_client(tmp_path, monkeypatch)

        resp = client.get("/recruitment")

        assert resp.status_code == 200
        for text in ("Recruitment", "New Candidate", "Edit Candidate", "Delete Candidate", "Import CV", "Open CV", "Clear Filters", "Refresh"):
            assert text in resp.text

    def test_api_crud_filter_and_validation(self, tmp_path, monkeypatch):
        client = _api_client(tmp_path, monkeypatch)

        invalid = client.post("/api/recruitment/candidates", json={"full_name": "No Contact"})
        assert invalid.status_code == 400
        assert "Email or phone" in invalid.json()["error"]

        created = client.post(
            "/api/recruitment/candidates",
            json={
                "full_name": "Jane Candidate",
                "email": "jane@example.test",
                "country": "Spain",
                "skills": "ABAP debugging",
                "sap_modules": "SAP IS-U Billing",
                "languages": "English, Spanish",
                "work_mode": "Remote",
                "rate_hour": 50,
                "rate_day": 400,
            },
        )
        assert created.status_code == 200
        candidate = created.json()
        assert candidate["id"]

        listed = client.get(
            "/api/recruitment/candidates",
            params={
                "search": "jane",
                "skill_text": "debug",
                "sap_module_text": "billing",
                "language_text": "spanish",
                "country": "Spain",
                "work_mode": "Remote",
                "max_hourly_rate": "55",
                "max_daily_rate": "450",
            },
        )
        assert listed.status_code == 200
        assert listed.json()["count"] == 1

        updated = client.put(
            f"/api/recruitment/candidates/{candidate['id']}",
            json={"phone": "+34 600 111 222", "full_name": "Jane Candidate"},
        )
        assert updated.status_code == 200
        assert updated.json()["phone"] == "+34 600 111 222"
        assert updated.json()["email"] == "jane@example.test"

        deleted = client.delete(f"/api/recruitment/candidates/{candidate['id']}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        assert client.get("/api/recruitment/candidates").json()["count"] == 0

    def test_api_import_cv_prefills_but_does_not_auto_save(self, tmp_path, monkeypatch):
        client = _api_client(tmp_path, monkeypatch)
        content = b"Jane Candidate\nSenior SAP IS-U Consultant\njane@example.test\n"

        resp = client.post(
            "/api/recruitment/cv/import",
            files={"file": ("candidate.txt", content, "text/plain")},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is False
        assert data["candidate"]["full_name"] == "Jane Candidate"
        assert data["candidate"]["email"] == "jane@example.test"
        assert Path(data["candidate"]["cv_file_path"]).exists()
        assert client.get("/api/recruitment/candidates").json()["count"] == 0

    def test_api_import_rejects_unsupported_files(self, tmp_path, monkeypatch):
        client = _api_client(tmp_path, monkeypatch)

        resp = client.post(
            "/api/recruitment/cv/import",
            files={"file": ("candidate.exe", b"nope", "application/octet-stream")},
        )

        assert resp.status_code == 400
        assert "Unsupported CV file type" in resp.json()["error"]

    def test_open_cv_reports_missing_file_cleanly(self, tmp_path, monkeypatch):
        client = _api_client(tmp_path, monkeypatch)
        created = client.post(
            "/api/recruitment/candidates",
            json={
                "full_name": "Jane Candidate",
                "email": "jane@example.test",
                "cv_file_path": str(tmp_path / "missing.pdf"),
            },
        ).json()

        resp = client.post(f"/api/recruitment/candidates/{created['id']}/open-cv")

        assert resp.status_code == 404
        assert "CV file is missing" in resp.json()["error"]

    def test_ui_metadata_matches_requested_controls(self):
        from ui.recruitment.candidate_form import CURRENCY_OPTIONS, FORM_FIELDS, WORK_MODE_OPTIONS
        from ui.recruitment.candidates_tab import ACTION_BUTTONS, FILTER_FIELDS, TABLE_COLUMNS

        assert "full_name" in FORM_FIELDS
        assert "cv_text" in FORM_FIELDS
        assert WORK_MODE_OPTIONS == ("Remote", "Hybrid", "Onsite", "Any")
        assert CURRENCY_OPTIONS == ("EUR", "USD", "GBP", "Other")
        assert "sap_module_text" in FILTER_FIELDS
        assert "updated_at" in TABLE_COLUMNS
        for action in ("New Candidate", "Edit Candidate", "Delete Candidate", "Import CV", "Open CV", "Clear Filters", "Refresh"):
            assert action in ACTION_BUTTONS
