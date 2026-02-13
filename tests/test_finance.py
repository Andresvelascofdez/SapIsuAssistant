"""Tests for the personal finance module."""
import json
from pathlib import Path

import pytest

from src.finance.storage.finance_repository import (
    DEFAULT_CATEGORIES,
    ExpenseCategory,
    FinanceRepository,
    FinanceSettings,
    Invoice,
    InvoiceItem,
    _round2,
)


# ── Repository: Settings ──


class TestFinanceSettings:
    def test_default_settings_seeded(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        s = repo.get_settings()
        assert isinstance(s, FinanceSettings)
        assert s.tax_rate_default == 0.15
        assert s.company_name == ""

    def test_update_company_info(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        s = repo.update_settings(company_name="Acme Corp", company_address="123 Main St")
        assert s.company_name == "Acme Corp"
        assert s.company_address == "123 Main St"

    def test_update_tax_rate(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        s = repo.update_settings(tax_rate_default=0.21)
        assert s.tax_rate_default == 0.21

    def test_update_preserves_other_fields(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        repo.update_settings(company_name="Foo")
        s = repo.update_settings(company_email="a@b.com")
        assert s.company_name == "Foo"
        assert s.company_email == "a@b.com"

    def test_update_ignores_unknown_fields(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        s = repo.update_settings(unknown_field="ignored")
        assert s.company_name == ""  # unchanged


# ── Repository: Categories ──


class TestExpenseCategories:
    def test_default_categories_seeded(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories(active_only=False)
        assert len(cats) == len(DEFAULT_CATEGORIES)
        names = [c.name for c in cats]
        for dc in DEFAULT_CATEGORIES:
            assert dc in names

    def test_create_category(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cat = repo.create_category("Travel")
        assert cat.name == "Travel"
        assert cat.is_active is True

    def test_rename_category(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cat = repo.create_category("Temp")
        renamed = repo.rename_category(cat.id, "Renamed")
        assert renamed.name == "Renamed"

    def test_toggle_category(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        cat = cats[0]
        toggled = repo.toggle_category(cat.id, False)
        assert toggled.is_active is False
        toggled = repo.toggle_category(cat.id, True)
        assert toggled.is_active is True

    def test_delete_category(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cat = repo.create_category("ToDelete")
        assert repo.delete_category(cat.id) is True
        cats = repo.list_categories(active_only=False)
        assert cat.id not in [c.id for c in cats]

    def test_delete_category_with_expenses_fails(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        cat = cats[0]
        repo.create_expense(period_year=2025, period_month=1, category_id=cat.id, amount=10.0)
        with pytest.raises(ValueError, match="expense"):
            repo.delete_category(cat.id)

    def test_delete_nonexistent_category(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        assert repo.delete_category(9999) is False

    def test_reorder_categories(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories(active_only=False)
        reversed_ids = [c.id for c in reversed(cats)]
        reordered = repo.reorder_categories(reversed_ids)
        assert reordered[0].id == reversed_ids[0]


# ── Repository: Documents ──


class TestDocuments:
    def test_create_and_get_document(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        doc = repo.create_document(
            original_file_name="receipt.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            storage_path="finance/uploads/2025/01/receipt.pdf",
            file_bytes=b"fake pdf content",
        )
        assert doc.original_file_name == "receipt.pdf"
        assert doc.sha256 is not None

        fetched = repo.get_document(doc.id)
        assert fetched.id == doc.id

    def test_delete_document(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        doc = repo.create_document(
            original_file_name="test.jpg",
            mime_type="image/jpeg",
            size_bytes=500,
            storage_path="finance/uploads/2025/01/test.jpg",
        )
        assert repo.delete_document(doc.id) is True
        assert repo.get_document(doc.id) is None

    def test_delete_document_unlinks_expense(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        doc = repo.create_document(
            original_file_name="r.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            storage_path="finance/uploads/2025/01/r.pdf",
        )
        cats = repo.list_categories()
        expense = repo.create_expense(
            period_year=2025, period_month=1,
            category_id=cats[0].id, amount=50.0,
            document_id=doc.id,
        )
        assert expense.document_id == doc.id
        repo.delete_document(doc.id)
        updated = repo.get_expense(expense.id)
        assert updated.document_id is None

    def test_update_document_ocr(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        doc = repo.create_document(
            original_file_name="scan.jpg",
            mime_type="image/jpeg",
            size_bytes=2048,
            storage_path="finance/uploads/2025/03/scan.jpg",
        )
        updated = repo.update_document_ocr(doc.id, "raw text", 42.50, "2025-03")
        assert updated.ocr_raw_text == "raw text"
        assert updated.ocr_detected_amount == 42.50
        assert updated.ocr_detected_date_iso == "2025-03"


# ── Repository: Expenses ──


class TestExpenses:
    def test_create_expense(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        e = repo.create_expense(
            period_year=2025, period_month=3,
            category_id=cats[0].id, amount=99.99,
            merchant="Amazon",
        )
        assert e.amount == 99.99
        assert e.merchant == "Amazon"
        assert e.currency == "EUR"
        assert e.category_name == cats[0].name

    def test_update_expense(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        e = repo.create_expense(
            period_year=2025, period_month=1,
            category_id=cats[0].id, amount=10.0,
        )
        updated = repo.update_expense(e.id, amount=20.0, merchant="NewMerchant")
        assert updated.amount == 20.0
        assert updated.merchant == "NewMerchant"

    def test_delete_expense(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        e = repo.create_expense(
            period_year=2025, period_month=1,
            category_id=cats[0].id, amount=10.0,
        )
        assert repo.delete_expense(e.id) is True
        assert repo.get_expense(e.id) is None

    def test_delete_nonexistent_expense(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        assert repo.delete_expense("nonexistent") is False

    def test_list_expenses_with_filters(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        repo.create_expense(period_year=2025, period_month=1, category_id=cats[0].id, amount=10.0)
        repo.create_expense(period_year=2025, period_month=2, category_id=cats[0].id, amount=20.0)
        repo.create_expense(period_year=2025, period_month=1, category_id=cats[1].id, amount=30.0)
        repo.create_expense(period_year=2024, period_month=1, category_id=cats[0].id, amount=40.0)

        # Filter by year
        results = repo.list_expenses(year=2025)
        assert len(results) == 3

        # Filter by year + month
        results = repo.list_expenses(year=2025, month=1)
        assert len(results) == 2

        # Filter by category
        results = repo.list_expenses(category_id=cats[1].id)
        assert len(results) == 1

    def test_sum_expenses(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        repo.create_expense(period_year=2025, period_month=1, category_id=cats[0].id, amount=10.0)
        repo.create_expense(period_year=2025, period_month=1, category_id=cats[0].id, amount=20.0)
        repo.create_expense(period_year=2025, period_month=2, category_id=cats[0].id, amount=30.0)

        assert repo.sum_expenses(year=2025, month=1) == 30.0
        assert repo.sum_expenses(year=2025) == 60.0
        assert repo.sum_expenses() == 60.0

    def test_count_expenses(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        repo.create_expense(period_year=2025, period_month=1, category_id=cats[0].id, amount=10.0)
        repo.create_expense(period_year=2025, period_month=1, category_id=cats[0].id, amount=20.0)
        assert repo.count_expenses(year=2025, month=1) == 2
        assert repo.count_expenses() == 2

    def test_document_not_required_flag(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        e = repo.create_expense(
            period_year=2025, period_month=1,
            category_id=cats[0].id, amount=5.0,
            document_not_required=True,
        )
        assert e.document_not_required is True
        assert e.document_id is None

    def test_expense_pagination(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        for i in range(10):
            repo.create_expense(
                period_year=2025, period_month=1,
                category_id=cats[0].id, amount=float(i + 1),
            )
        page1 = repo.list_expenses(limit=3, offset=0)
        assert len(page1) == 3
        page2 = repo.list_expenses(limit=3, offset=3)
        assert len(page2) == 3
        assert page1[0].id != page2[0].id


# ── Web API: Finance Settings ──


class TestFinanceSettingsAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.web.app import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_get_settings(self, client):
        resp = client.get("/api/finance/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_rate_default"] == 0.15

    def test_update_settings(self, client):
        resp = client.put(
            "/api/finance/settings",
            json={"company_name": "Test Corp", "tax_rate_default": 0.21},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_name"] == "Test Corp"
        assert data["tax_rate_default"] == 0.21

    def test_settings_page_loads(self, client):
        resp = client.get("/finance/settings")
        assert resp.status_code == 200


# ── Web API: Categories ──


class TestCategoriesAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.web.app import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_list_categories(self, client):
        resp = client.get("/api/finance/categories?active_only=false")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(DEFAULT_CATEGORIES)

    def test_create_category(self, client):
        resp = client.post("/api/finance/categories", json={"name": "Travel"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Travel"

    def test_create_category_empty_name_fails(self, client):
        resp = client.post("/api/finance/categories", json={"name": ""})
        assert resp.status_code == 400

    def test_rename_category(self, client):
        resp = client.post("/api/finance/categories", json={"name": "Temp"})
        cat_id = resp.json()["id"]
        resp = client.put(f"/api/finance/categories/{cat_id}", json={"name": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    def test_toggle_category(self, client):
        resp = client.get("/api/finance/categories?active_only=false")
        cat_id = resp.json()[0]["id"]
        resp = client.put(f"/api/finance/categories/{cat_id}/toggle", json={"active": False})
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_delete_category(self, client):
        resp = client.post("/api/finance/categories", json={"name": "ToDelete"})
        cat_id = resp.json()["id"]
        resp = client.delete(f"/api/finance/categories/{cat_id}")
        assert resp.status_code == 200

    def test_reorder_categories(self, client):
        resp = client.get("/api/finance/categories?active_only=false")
        ids = [c["id"] for c in resp.json()]
        reversed_ids = list(reversed(ids))
        resp = client.put("/api/finance/categories/reorder", json={"ordered_ids": reversed_ids})
        assert resp.status_code == 200
        result_ids = [c["id"] for c in resp.json()]
        assert result_ids[0] == reversed_ids[0]


# ── Web API: Expenses ──


class TestExpenseAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.web.app import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def _get_first_category_id(self, client):
        resp = client.get("/api/finance/categories")
        return resp.json()[0]["id"]

    def test_expenses_page_loads(self, client):
        resp = client.get("/finance/expenses")
        assert resp.status_code == 200

    def test_create_expense(self, client):
        cat_id = self._get_first_category_id(client)
        resp = client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 3,
            "category_id": cat_id, "amount": 42.50,
            "merchant": "Store",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["amount"] == 42.50
        assert data["merchant"] == "Store"
        assert data["currency"] == "EUR"

    def test_create_expense_missing_field(self, client):
        resp = client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 3,
        })
        assert resp.status_code == 400

    def test_list_expenses(self, client):
        cat_id = self._get_first_category_id(client)
        client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 1,
            "category_id": cat_id, "amount": 10.0,
        })
        client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 1,
            "category_id": cat_id, "amount": 20.0,
        })
        resp = client.get("/api/finance/expenses?year=2025&month=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["expenses"]) == 2
        assert data["total"] == 30.0
        assert data["count"] == 2

    def test_update_expense(self, client):
        cat_id = self._get_first_category_id(client)
        resp = client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 1,
            "category_id": cat_id, "amount": 10.0,
        })
        expense_id = resp.json()["id"]
        resp = client.put(f"/api/finance/expenses/{expense_id}", json={"amount": 99.0})
        assert resp.status_code == 200
        assert resp.json()["amount"] == 99.0

    def test_delete_expense(self, client):
        cat_id = self._get_first_category_id(client)
        resp = client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 1,
            "category_id": cat_id, "amount": 10.0,
        })
        expense_id = resp.json()["id"]
        resp = client.delete(f"/api/finance/expenses/{expense_id}")
        assert resp.status_code == 200
        resp = client.get("/api/finance/expenses")
        assert resp.json()["count"] == 0

    def test_export_csv(self, client):
        cat_id = self._get_first_category_id(client)
        client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 3,
            "category_id": cat_id, "amount": 55.0,
            "merchant": "TestMerchant",
        })
        resp = client.get("/api/finance/expenses/export-csv?year=2025")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        content = resp.text
        assert "TestMerchant" in content
        assert "55.00" in content


# ── Web API: Documents ──


class TestDocumentAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.web.app import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_upload_document(self, client):
        resp = client.post(
            "/api/finance/upload",
            files={"file": ("receipt.pdf", b"fake pdf", "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["original_file_name"] == "receipt.pdf"
        assert data["sha256"] is not None

    def test_download_document(self, client, tmp_path):
        resp = client.post(
            "/api/finance/upload",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
        doc_id = resp.json()["id"]
        resp = client.get(f"/api/finance/documents/{doc_id}/download")
        assert resp.status_code == 200
        assert resp.content == b"hello world"

    def test_delete_document(self, client):
        resp = client.post(
            "/api/finance/upload",
            files={"file": ("test.txt", b"content", "text/plain")},
        )
        doc_id = resp.json()["id"]
        resp = client.delete(f"/api/finance/documents/{doc_id}")
        assert resp.status_code == 200
        resp = client.get(f"/api/finance/documents/{doc_id}/download")
        assert resp.status_code == 404

    def test_download_nonexistent_document(self, client):
        resp = client.get("/api/finance/documents/nonexistent/download")
        assert resp.status_code == 404


# ── Repository: Invoice Calculations ──


class TestInvoiceCalculations:
    def test_round2(self):
        assert _round2(1.005) == 1.0
        assert _round2(1.015) == 1.01
        assert _round2(10.125) == 10.12
        assert _round2(99.999) == 100.0
        assert _round2(0.0) == 0.0

    def test_line_total_calculation(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=3,
            client_name="Test Client", invoice_number="INV-001",
            items=[{"description": "Dev work", "quantity": 10, "unit_price": 75.0, "unit": "HOURS"}],
        )
        assert inv.subtotal == 750.0
        assert inv.total == 750.0

    def test_subtotal_multiple_items(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=3,
            client_name="Client", invoice_number="INV-002",
            items=[
                {"description": "Dev", "quantity": 8, "unit_price": 100.0, "unit": "HOURS"},
                {"description": "Design", "quantity": 4, "unit_price": 80.0, "unit": "HOURS"},
                {"description": "Consulting", "quantity": 2, "unit_price": 150.0, "unit": "DAYS"},
            ],
        )
        expected_subtotal = _round2(800.0 + 320.0 + 300.0)
        assert inv.subtotal == expected_subtotal
        assert inv.total == expected_subtotal  # 0% VAT

    def test_vat_calculation(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=3,
            client_name="Client", invoice_number="INV-003",
            vat_rate=0.21,
            items=[{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        )
        assert inv.subtotal == 1000.0
        assert inv.vat_rate == 0.21
        assert inv.vat_amount == _round2(1000.0 * 0.21)  # 210.0
        assert inv.total == _round2(1000.0 + 210.0)  # 1210.0

    def test_zero_vat(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=3,
            client_name="Client", invoice_number="INV-004",
            vat_rate=0.0,
            items=[{"description": "Work", "quantity": 5, "unit_price": 200.0, "unit": "HOURS"}],
        )
        assert inv.vat_rate == 0.0
        assert inv.vat_amount == 0.0
        assert inv.total == inv.subtotal == 1000.0

    def test_no_items_invoice(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=3,
            client_name="Client", invoice_number="INV-005",
        )
        assert inv.subtotal == 0.0
        assert inv.vat_amount == 0.0
        assert inv.total == 0.0


# ── Repository: Invoice CRUD ──


class TestInvoiceCRUD:
    def test_create_invoice_with_items(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=6,
            client_name="Acme Corp", invoice_number="2025-06-001",
            client_address="123 Main St",
            vat_rate=0.21,
            notes="Monthly consultancy",
            items=[
                {"description": "Development", "quantity": 40, "unit_price": 75.0, "unit": "HOURS"},
                {"description": "Code review", "quantity": 8, "unit_price": 75.0, "unit": "HOURS"},
            ],
        )
        assert isinstance(inv, Invoice)
        assert inv.client_name == "Acme Corp"
        assert inv.client_address == "123 Main St"
        assert inv.invoice_number == "2025-06-001"
        assert inv.status == "PENDING"
        assert inv.currency == "EUR"
        assert inv.notes == "Monthly consultancy"

        items = repo.get_invoice_items(inv.id)
        assert len(items) == 2
        assert items[0].description == "Development"
        assert items[0].quantity == 40
        assert items[0].unit == "HOURS"
        assert items[0].unit_price == 75.0
        assert items[0].line_total == 3000.0

    def test_get_invoice(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=1,
            client_name="Client A", invoice_number="INV-A01",
        )
        fetched = repo.get_invoice(inv.id)
        assert fetched is not None
        assert fetched.id == inv.id
        assert fetched.client_name == "Client A"

    def test_get_nonexistent_invoice(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        assert repo.get_invoice("nonexistent") is None

    def test_update_invoice_fields(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=1,
            client_name="Old Client", invoice_number="INV-OLD",
        )
        updated = repo.update_invoice(inv.id, client_name="New Client", status="PAID")
        assert updated.client_name == "New Client"
        assert updated.status == "PAID"

    def test_update_invoice_vat_recalculates(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=1,
            client_name="Client", invoice_number="INV-VAT",
            vat_rate=0.0,
            items=[{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        )
        assert inv.total == 1000.0
        assert inv.vat_amount == 0.0

        updated = repo.update_invoice(inv.id, vat_rate=0.21)
        assert updated.vat_rate == 0.21
        assert updated.vat_amount == 210.0
        assert updated.total == 1210.0

    def test_set_invoice_items_replaces_and_recalculates(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=1,
            client_name="Client", invoice_number="INV-ITEMS",
            vat_rate=0.10,
            items=[{"description": "Old work", "quantity": 5, "unit_price": 100.0, "unit": "HOURS"}],
        )
        assert inv.subtotal == 500.0

        repo.set_invoice_items(inv.id, [
            {"description": "New work", "quantity": 10, "unit_price": 50.0, "unit": "HOURS"},
            {"description": "Extra", "quantity": 2, "unit_price": 200.0, "unit": "DAYS"},
        ])
        updated = repo.get_invoice(inv.id)
        assert updated.subtotal == _round2(500.0 + 400.0)  # 900.0
        assert updated.vat_amount == _round2(900.0 * 0.10)  # 90.0
        assert updated.total == _round2(900.0 + 90.0)  # 990.0

        items = repo.get_invoice_items(inv.id)
        assert len(items) == 2
        assert items[0].description == "New work"

    def test_delete_invoice(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=1,
            client_name="Client", invoice_number="INV-DEL",
            items=[{"description": "Work", "quantity": 1, "unit_price": 100.0, "unit": "HOURS"}],
        )
        assert repo.delete_invoice(inv.id) is True
        assert repo.get_invoice(inv.id) is None
        assert repo.get_invoice_items(inv.id) == []

    def test_delete_nonexistent_invoice(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        assert repo.delete_invoice("nonexistent") is False

    def test_list_invoices_with_filters(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        repo.create_invoice(period_year=2025, period_month=1, client_name="Alpha", invoice_number="A1")
        repo.create_invoice(period_year=2025, period_month=2, client_name="Beta", invoice_number="B1")
        repo.create_invoice(period_year=2025, period_month=1, client_name="Alpha Corp", invoice_number="A2")
        repo.create_invoice(period_year=2024, period_month=1, client_name="Gamma", invoice_number="G1")

        assert len(repo.list_invoices(year=2025)) == 3
        assert len(repo.list_invoices(year=2025, month=1)) == 2
        assert len(repo.list_invoices(client="Alpha")) == 2
        assert len(repo.list_invoices(year=2024)) == 1

    def test_sum_invoices(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        repo.create_invoice(
            period_year=2025, period_month=1, client_name="A", invoice_number="I1",
            items=[{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        )
        repo.create_invoice(
            period_year=2025, period_month=1, client_name="B", invoice_number="I2",
            items=[{"description": "Work", "quantity": 5, "unit_price": 200.0, "unit": "HOURS"}],
        )
        assert repo.sum_invoices(year=2025, month=1) == 2000.0
        assert repo.count_invoices(year=2025) == 2

    def test_sum_pending_invoices(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv1 = repo.create_invoice(
            period_year=2025, period_month=1, client_name="A", invoice_number="I1",
            items=[{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        )
        inv2 = repo.create_invoice(
            period_year=2025, period_month=1, client_name="B", invoice_number="I2",
            items=[{"description": "Work", "quantity": 5, "unit_price": 200.0, "unit": "HOURS"}],
        )
        repo.update_invoice(inv1.id, status="PAID")
        assert repo.sum_pending_invoices(year=2025) == 1000.0


# ── Invoice PDF Generation ──


class TestInvoicePDF:
    def test_generate_pdf_creates_file(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        repo.update_settings(
            company_name="Test Corp",
            company_address="123 Test St",
            company_tax_id="ES12345678A",
        )
        inv = repo.create_invoice(
            period_year=2025, period_month=6,
            client_name="Client Co", invoice_number="2025-001",
            client_address="456 Client Ave",
            vat_rate=0.21,
            notes="Thank you for your business.",
            items=[
                {"description": "Development", "quantity": 40, "unit_price": 75.0, "unit": "HOURS"},
                {"description": "Design", "quantity": 16, "unit_price": 60.0, "unit": "HOURS"},
            ],
        )
        items = repo.get_invoice_items(inv.id)
        settings = repo.get_settings()

        from src.finance.pdf.invoice_pdf import generate_invoice_pdf
        pdf_path = tmp_path / "output" / "test_invoice.pdf"
        result = generate_invoice_pdf(inv, items, settings, pdf_path)

        assert result == pdf_path
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
        # Basic PDF validation: starts with %PDF
        content = pdf_path.read_bytes()
        assert content[:5] == b"%PDF-"

    def test_generate_pdf_no_vat(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=1,
            client_name="Client", invoice_number="2025-NOVAT",
            vat_rate=0.0,
            items=[{"description": "Work", "quantity": 10, "unit_price": 50.0, "unit": "HOURS"}],
        )
        items = repo.get_invoice_items(inv.id)
        settings = repo.get_settings()

        from src.finance.pdf.invoice_pdf import generate_invoice_pdf
        pdf_path = tmp_path / "no_vat.pdf"
        result = generate_invoice_pdf(inv, items, settings, pdf_path)
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_generate_pdf_empty_items(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        inv = repo.create_invoice(
            period_year=2025, period_month=1,
            client_name="Client", invoice_number="2025-EMPTY",
        )
        items = repo.get_invoice_items(inv.id)
        settings = repo.get_settings()

        from src.finance.pdf.invoice_pdf import generate_invoice_pdf
        pdf_path = tmp_path / "empty.pdf"
        result = generate_invoice_pdf(inv, items, settings, pdf_path)
        assert pdf_path.exists()


# ── Web API: Invoices ──


class TestInvoiceAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.web.app import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_invoices_page_loads(self, client):
        resp = client.get("/finance/invoices")
        assert resp.status_code == 200

    def test_invoice_new_page_loads(self, client):
        resp = client.get("/finance/invoices/new")
        assert resp.status_code == 200

    def test_create_invoice(self, client):
        resp = client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 6,
            "client_name": "Test Client", "invoice_number": "INV-2025-001",
            "vat_rate": 0.21,
            "items": [
                {"description": "Dev work", "quantity": 40, "unit_price": 75.0, "unit": "HOURS"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["client_name"] == "Test Client"
        assert data["invoice_number"] == "INV-2025-001"
        assert data["subtotal"] == 3000.0
        assert data["vat_amount"] == 630.0
        assert data["total"] == 3630.0
        assert data["status"] == "PENDING"

    def test_create_invoice_missing_field(self, client):
        resp = client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 6,
            "client_name": "Client",
            # missing invoice_number
        })
        assert resp.status_code == 400

    def test_get_invoice_with_items(self, client):
        resp = client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 1,
            "client_name": "Client", "invoice_number": "INV-GET",
            "items": [
                {"description": "Work A", "quantity": 5, "unit_price": 100.0, "unit": "HOURS"},
                {"description": "Work B", "quantity": 3, "unit_price": 80.0, "unit": "DAYS"},
            ],
        })
        invoice_id = resp.json()["id"]
        resp = client.get(f"/api/finance/invoices/{invoice_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == invoice_id
        assert "items" in data
        assert len(data["items"]) == 2
        assert data["items"][0]["description"] == "Work A"

    def test_get_nonexistent_invoice(self, client):
        resp = client.get("/api/finance/invoices/nonexistent")
        assert resp.status_code == 404

    def test_update_invoice(self, client):
        resp = client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 1,
            "client_name": "Old Name", "invoice_number": "INV-UPD",
            "items": [{"description": "Work", "quantity": 10, "unit_price": 50.0, "unit": "HOURS"}],
        })
        invoice_id = resp.json()["id"]
        resp = client.put(f"/api/finance/invoices/{invoice_id}", json={
            "client_name": "New Name",
            "status": "PAID",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["client_name"] == "New Name"
        assert data["status"] == "PAID"

    def test_update_invoice_with_items(self, client):
        resp = client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 1,
            "client_name": "Client", "invoice_number": "INV-UPDITEMS",
            "items": [{"description": "Old", "quantity": 1, "unit_price": 100.0, "unit": "HOURS"}],
        })
        invoice_id = resp.json()["id"]
        resp = client.put(f"/api/finance/invoices/{invoice_id}", json={
            "items": [
                {"description": "New A", "quantity": 10, "unit_price": 75.0, "unit": "HOURS"},
                {"description": "New B", "quantity": 5, "unit_price": 50.0, "unit": "DAYS"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["subtotal"] == 1000.0  # 750 + 250

    def test_delete_invoice(self, client):
        resp = client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 1,
            "client_name": "Client", "invoice_number": "INV-DEL",
        })
        invoice_id = resp.json()["id"]
        resp = client.delete(f"/api/finance/invoices/{invoice_id}")
        assert resp.status_code == 200
        resp = client.get(f"/api/finance/invoices/{invoice_id}")
        assert resp.status_code == 404

    def test_delete_nonexistent_invoice(self, client):
        resp = client.delete("/api/finance/invoices/nonexistent")
        assert resp.status_code == 404

    def test_list_invoices(self, client):
        client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 1,
            "client_name": "A", "invoice_number": "I1",
            "items": [{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        })
        client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 1,
            "client_name": "B", "invoice_number": "I2",
            "items": [{"description": "Work", "quantity": 5, "unit_price": 200.0, "unit": "HOURS"}],
        })
        resp = client.get("/api/finance/invoices?year=2025&month=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["invoices"]) == 2
        assert data["total"] == 2000.0
        assert data["count"] == 2
        assert data["pending"] == 2000.0

    def test_list_invoices_with_client_filter(self, client):
        client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 1,
            "client_name": "Alpha Corp", "invoice_number": "A1",
        })
        client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 1,
            "client_name": "Beta Inc", "invoice_number": "B1",
        })
        resp = client.get("/api/finance/invoices?client=Alpha")
        assert resp.status_code == 200
        assert len(resp.json()["invoices"]) == 1

    def test_invoice_edit_page_loads(self, client):
        resp = client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 1,
            "client_name": "Client", "invoice_number": "INV-PAGE",
        })
        invoice_id = resp.json()["id"]
        resp = client.get(f"/finance/invoices/{invoice_id}/edit")
        assert resp.status_code == 200

    def test_generate_pdf(self, client):
        resp = client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 6,
            "client_name": "PDF Client", "invoice_number": "PDF-001",
            "vat_rate": 0.21,
            "items": [
                {"description": "Consulting", "quantity": 20, "unit_price": 100.0, "unit": "HOURS"},
            ],
        })
        invoice_id = resp.json()["id"]
        assert resp.json()["document_id"] is None

        resp = client.post(f"/api/finance/invoices/{invoice_id}/generate-pdf")
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] is not None

        # Verify the document can be downloaded
        doc_id = data["document_id"]
        resp = client.get(f"/api/finance/documents/{doc_id}/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"

    def test_generate_pdf_nonexistent_invoice(self, client):
        resp = client.post("/api/finance/invoices/nonexistent/generate-pdf")
        assert resp.status_code == 404

    def test_export_invoices_csv(self, client):
        client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 3,
            "client_name": "CSV Client", "invoice_number": "CSV-001",
            "vat_rate": 0.21,
            "items": [{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        })
        resp = client.get("/api/finance/invoices/export-csv?year=2025")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        content = resp.text
        assert "CSV Client" in content
        assert "CSV-001" in content
        assert "1210.00" in content  # total with 21% VAT on 1000


# ── Repository: Summaries ──


class TestSummary:
    def test_monthly_summary_empty(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        s = repo.get_monthly_summary(2025, 1)
        assert s["incomes"] == 0.0
        assert s["expenses"] == 0.0
        assert s["profit"] == 0.0
        assert s["tax"] == 0.0
        assert s["net"] == 0.0
        assert s["net_business"] == 0.0
        assert s["tax_rate"] == 0.15

    def test_monthly_summary_with_data(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        # Create invoice (income)
        repo.create_invoice(
            period_year=2025, period_month=3,
            client_name="Client", invoice_number="INV-1",
            items=[{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        )
        # Create expense
        repo.create_expense(period_year=2025, period_month=3, category_id=cats[0].id, amount=300.0)
        s = repo.get_monthly_summary(2025, 3)
        assert s["incomes"] == 1000.0
        assert s["expenses"] == 300.0
        assert s["profit"] == 700.0
        assert s["tax"] == _round2(1000.0 * 0.15)  # 150.0
        assert s["net"] == _round2(1000.0 - 150.0)  # 850.0 (net = incomes - tax)
        assert s["net_business"] == _round2(1000.0 - 300.0 - 150.0)  # 550.0 (net_business = incomes - expenses - tax)

    def test_monthly_summary_custom_tax_rate(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        repo.create_invoice(
            period_year=2025, period_month=1,
            client_name="A", invoice_number="I1",
            items=[{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        )
        repo.create_expense(period_year=2025, period_month=1, category_id=cats[0].id, amount=200.0)
        s = repo.get_monthly_summary(2025, 1, tax_rate=0.25)
        assert s["profit"] == 800.0
        assert s["tax_rate"] == 0.25
        assert s["tax"] == _round2(1000.0 * 0.25)  # 250.0
        assert s["net"] == _round2(1000.0 - 250.0)  # 750.0 (net = incomes - tax)
        assert s["net_business"] == _round2(1000.0 - 200.0 - 250.0)  # 550.0 (net_business = incomes - expenses - tax)

    def test_monthly_summary_negative_profit_no_tax(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        # Only expenses, no income
        repo.create_expense(period_year=2025, period_month=1, category_id=cats[0].id, amount=500.0)
        s = repo.get_monthly_summary(2025, 1)
        assert s["profit"] == -500.0
        assert s["tax"] == 0.0  # no tax on negative profit
        assert s["net"] == 0.0  # net = incomes - tax; no income means net = 0
        assert s["net_business"] == -500.0  # net_business = 0 - 500 - 0 = -500

    def test_yearly_summary_returns_12_months(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        months = repo.get_yearly_summary(2025)
        assert len(months) == 12
        assert months[0]["month"] == 1
        assert months[11]["month"] == 12

    def test_yearly_summary_with_data(self, tmp_path):
        repo = FinanceRepository(tmp_path / "fin.db")
        cats = repo.list_categories()
        repo.create_invoice(
            period_year=2025, period_month=3,
            client_name="A", invoice_number="I1",
            items=[{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        )
        repo.create_expense(period_year=2025, period_month=3, category_id=cats[0].id, amount=300.0)
        months = repo.get_yearly_summary(2025)
        march = months[2]  # 0-indexed, month 3
        assert march["incomes"] == 1000.0
        assert march["expenses"] == 300.0
        assert march["profit"] == 700.0
        # Other months should be zeros
        assert months[0]["incomes"] == 0.0
        assert months[0]["profit"] == 0.0


# ── Web API: Summary ──


class TestSummaryAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.web.app import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_summary_page_loads(self, client):
        resp = client.get("/finance/summary")
        assert resp.status_code == 200

    def test_yearly_summary_api(self, client):
        resp = client.get("/api/finance/summary?year=2025")
        assert resp.status_code == 200
        data = resp.json()
        assert "months" in data
        assert len(data["months"]) == 12
        assert "totals" in data

    def test_monthly_summary_api(self, client):
        resp = client.get("/api/finance/summary?year=2025&month=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["months"]) == 1
        assert data["months"][0]["month"] == 3

    def test_summary_with_custom_tax_rate(self, client):
        resp = client.get("/api/finance/summary?year=2025&tax_rate=0.25")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["tax_rate"] == 0.25

    def test_summary_with_data(self, client):
        # Create an invoice (income)
        client.post("/api/finance/invoices", json={
            "period_year": 2025, "period_month": 3,
            "client_name": "Client", "invoice_number": "INV-SUM",
            "items": [{"description": "Work", "quantity": 10, "unit_price": 100.0, "unit": "HOURS"}],
        })
        # Create an expense
        cats_resp = client.get("/api/finance/categories")
        cat_id = cats_resp.json()[0]["id"]
        client.post("/api/finance/expenses", json={
            "period_year": 2025, "period_month": 3,
            "category_id": cat_id, "amount": 300.0,
        })
        resp = client.get("/api/finance/summary?year=2025&month=3")
        data = resp.json()
        m = data["months"][0]
        assert m["incomes"] == 1000.0
        assert m["expenses"] == 300.0
        assert m["profit"] == 700.0


# ── OCR: Text Parsing ──


class TestOCRParsing:
    def test_extract_dates_iso(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("Invoice date: 2025-03-15")
        assert (2025, 3) in dates

    def test_extract_dates_european(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("Fecha: 15/03/2025")
        assert (2025, 3) in dates

    def test_extract_dates_dotted(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("Datum: 15.03.2025")
        assert (2025, 3) in dates

    def test_extract_dates_no_dates(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("No dates here")
        assert len(dates) == 0

    def test_extract_amounts_with_keyword(self):
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("TOTAL: 42.50")
        assert 42.50 in amounts

    def test_extract_amounts_eur(self):
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("EUR 1,234.56")
        assert 1234.56 in amounts

    def test_extract_amounts_european_format(self):
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("IMPORTE: 1.234,56")
        assert 1234.56 in amounts

    def test_extract_amounts_no_amounts(self):
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("No amounts here")
        assert len(amounts) == 0

    def test_parse_number_us_format(self):
        from src.finance.ocr.ocr_service import _parse_number
        assert _parse_number("1,234.56") == 1234.56

    def test_parse_number_european_format(self):
        from src.finance.ocr.ocr_service import _parse_number
        assert _parse_number("1.234,56") == 1234.56

    def test_parse_number_simple(self):
        from src.finance.ocr.ocr_service import _parse_number
        assert _parse_number("42.50") == 42.50

    def test_parse_ocr_text(self):
        from src.finance.ocr.ocr_service import _parse_ocr_text
        result = _parse_ocr_text("Factura 2025-03-15\nTOTAL: 99.50\nOther text")
        assert result["suggested_amount"] == 99.50
        assert result["suggested_year"] == 2025
        assert result["suggested_month"] == 3

    def test_parse_ocr_text_empty(self):
        from src.finance.ocr.ocr_service import _parse_ocr_text
        result = _parse_ocr_text("")
        assert result["raw_text"] == ""
        assert result["suggested_amount"] is None
        assert result["suggested_year"] is None

    def test_pdf_text_extraction(self, tmp_path):
        """Test OCR extract_from_pdf with a text-based PDF."""
        # Create a simple PDF with text using reportlab
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet

        pdf_path = tmp_path / "test_ocr.pdf"
        doc = SimpleDocTemplate(str(pdf_path))
        styles = getSampleStyleSheet()
        elements = [
            Paragraph("Invoice 2025-06-15", styles["Normal"]),
            Paragraph("TOTAL: 250.00 EUR", styles["Normal"]),
        ]
        doc.build(elements)

        from src.finance.ocr.ocr_service import extract_from_pdf
        result = extract_from_pdf(pdf_path)
        assert result["raw_text"] != ""
        assert result["suggested_amount"] is not None
        assert result["suggested_year"] == 2025
        assert result["suggested_month"] == 6


# ── Web API: OCR ──


class TestOCRAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.web.app import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_ocr_nonexistent_document(self, client):
        resp = client.post("/api/finance/ocr/nonexistent")
        assert resp.status_code == 404

    def test_ocr_unsupported_mime_type(self, client):
        # Upload a non-image, non-pdf file
        resp = client.post(
            "/api/finance/upload",
            files={"file": ("data.csv", b"col1,col2\na,b", "text/csv")},
        )
        doc_id = resp.json()["id"]
        resp = client.post(f"/api/finance/ocr/{doc_id}")
        assert resp.status_code == 400
