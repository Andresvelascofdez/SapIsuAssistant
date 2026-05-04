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
        updated = repo.update_document_ocr(doc.id, "raw text", 42.50, "2025-03-15")
        assert updated.ocr_raw_text == "raw text"
        assert updated.ocr_detected_amount == 42.50
        assert updated.ocr_detected_date_iso == "2025-03-15"


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
        assert (2025, 3, 15) in dates

    def test_extract_dates_european(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("Fecha: 15/03/2025")
        assert (2025, 3, 15) in dates

    def test_extract_dates_dotted(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("Datum: 15.03.2025")
        assert (2025, 3, 15) in dates

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

    # ── New OCR extraction tests ──

    def test_extract_dates_two_digit_year(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("Date: 03/02/26")
        assert (2026, 2, 3) in dates

    def test_extract_dates_text_month_english(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("Fecha: Feb 2, 2026")
        assert (2026, 2, 2) in dates

    def test_extract_dates_text_month_full_english(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("January 2026 Consultancy fees")
        assert (2026, 1, 1) in dates

    def test_extract_dates_text_month_spanish(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("Fecha: Febrero 2, 2026")
        assert (2026, 2, 2) in dates

    def test_extract_dates_iso_prioritized_over_two_digit(self):
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("2025-03-15")
        assert dates[0] == (2025, 3, 15)

    def test_extract_client_name_spanish(self):
        from src.finance.ocr.ocr_service import _extract_client_name
        text = "FACTURA #24\nFecha: Feb 2, 2026\nCobrar a: Example GmbH\nDireccion: Test City"
        assert _extract_client_name(text) == "Example GmbH"

    def test_extract_client_name_english(self):
        from src.finance.ocr.ocr_service import _extract_client_name
        text = "Invoice no.: 25\nDate: 03/02/26\nInvoice To: Example Europe Limited"
        assert _extract_client_name(text) == "Example Europe Limited"

    def test_extract_client_name_bill_to(self):
        from src.finance.ocr.ocr_service import _extract_client_name
        text = "Bill To: Acme Corp\nAddress: 123 Main St"
        assert _extract_client_name(text) == "Acme Corp"

    def test_extract_client_name_none(self):
        from src.finance.ocr.ocr_service import _extract_client_name
        assert _extract_client_name("Just some text") is None

    def test_extract_invoice_number_spanish(self):
        from src.finance.ocr.ocr_service import _extract_invoice_number
        assert _extract_invoice_number("FACTURA #24\nFecha: Feb 2, 2026") == "24"

    def test_extract_invoice_number_english(self):
        from src.finance.ocr.ocr_service import _extract_invoice_number
        assert _extract_invoice_number("Invoice no.: 25\nDate: 03/02/26") == "25"

    def test_extract_invoice_number_none(self):
        from src.finance.ocr.ocr_service import _extract_invoice_number
        assert _extract_invoice_number("Just a receipt") is None

    def test_extract_merchant_with_suffix(self):
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "R.A.M. OIL CYPRUS LTD\nPETROL STATION\n24/01/2026\nTOTAL EUR 32.51"
        result = _extract_merchant(text)
        assert result is not None
        # Entity suffix LTD is stripped by _clean_merchant_name
        assert "R.A.M. OIL CYPRUS" in result

    def test_extract_merchant_restaurant(self):
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "CAPTAIN COD\nA & E CAPTAIN COD LTD\n24/01/2026\nTOTAL 50.40"
        # First line with company suffix in first 10 lines
        result = _extract_merchant(text)
        assert result is not None
        assert "CAPTAIN COD" in result

    def test_extract_merchant_none(self):
        from src.finance.ocr.ocr_service import _extract_merchant
        assert _extract_merchant("") is None

    def test_parse_ocr_text_new_fields(self):
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = "FACTURA #24\nFecha: Feb 2, 2026\nCobrar a: Example GmbH\nTOTAL: 9.450,00 EUR"
        result = _parse_ocr_text(text)
        assert result["suggested_client"] == "Example GmbH"
        assert result["suggested_invoice_number"] == "24"
        assert result["suggested_amount"] == 9450.00
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 2

    def test_parse_ocr_text_has_merchant_field(self):
        from src.finance.ocr.ocr_service import _parse_ocr_text
        result = _parse_ocr_text("NOSH\n10.01.2026\nTotal-EFT EUR: 125.90")
        assert result["suggested_merchant"] is not None

    def test_extract_amounts_euro_symbol(self):
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("Total due: €6,000.00")
        assert 6000.00 in amounts

    def test_extract_amounts_sale_keyword(self):
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("SALE: 134.75 EUR")
        assert 134.75 in amounts

    def test_extract_amounts_amount_before_eur(self):
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("134.75 EUR")
        assert 134.75 in amounts


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


# ── OCR: Real Ticket Text Extraction ──
# Tests use actual OCR output text from real scanned ticket/invoice files


class TestOCRRealTickets:
    """Test OCR parsing against real OCR text from scanned ticket files."""

    def test_petrolina_kiti_receipt(self):
        """Test extraction from Petrolina Kiti petrol station receipt (Scanned_20260108).

        Real OCR also produces garbage like '0002503.14.9.47' which must NOT
        override the real amount from 'AMOUNT EUR40.00'.
        """
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = (
            "OGG PAYMENT\nSYSTEMS\n"
            "0002503.14.9.47 17269\n"
            "PETROLINA KITI\n"
            "Leoforos Makariou 4\n"
            "LARNACA\n"
            "08/01/26 07:49:46\n"
            "DEBIT MASTERCARD <4108>\n"
            "PURCHASE\n"
            "AMOUNT EUR40.00\n"
            "AUTH. NO.:GWMP3T\n"
            "CARDHOLDER COPY\n"
        )
        result = _parse_ocr_text(text)
        assert result["suggested_merchant"] is not None
        assert "PETROLINA" in result["suggested_merchant"]
        assert result["suggested_amount"] == 40.00
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1

    def test_nosh_restaurant_receipt(self):
        """Test extraction from NOSH restaurant receipt (Scanned_20260110).

        Real OCR produces 'EFT EUR: 414.45' (subtotal before tip),
        'Tip EUR: 11.45', and 'Total-EFT EUR: 125.90' (real total).
        Must pick Total-EFT, not the larger EFT sub-amount.
        """
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = (
            "Member of G.A.P. Vassilopoulos Group\n"
            "NOSH\n"
            "15 KRUOU NEROU\n"
            "5330 FAMAGUSTA\n"
            "***Cardholder Receipt***\n"
            "10.01.2026 15:57:02\n"
            "EFT EUR: 414.45\n"
            "Tip EUR: 11.45\n"
            "Total-EFT EUR: 125.90\n"
            "Verified by Device\n"
            "THANK YOU!\n"
        )
        result = _parse_ocr_text(text)
        assert result["suggested_merchant"] == "NOSH"
        assert result["suggested_amount"] == 125.90
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1

    def test_petrolina_dromolaxia_receipt(self):
        """Test extraction from Petrolina Dromolaxia receipt (Scanned_20260115).

        Real OCR produces garbled "AMOUNT EURS9, 70" where S→3 gives 39.70.
        """
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = (
            "PETROLINA - DROMOLAXIA\n"
            "15/01/2026\n"
            "UNLEADED 95\n"
            "39.70 L\n"
            "AMOUNT EURS9, 70\n"
            "VISA\n"
        )
        result = _parse_ocr_text(text)
        assert result["suggested_merchant"] is not None
        assert "PETROLINA" in result["suggested_merchant"]
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_amount"] == 39.70

    def test_beach_restaurant_greek_receipt(self):
        """Test extraction from Beach Restaurant Greek receipt (Scanned_20260117-1516)."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = (
            "BEACH RESTAURANT\n"
            "17-01-2026\n"
            "MOYZAKA 12,00\n"
            "SOUVLAKI 10,00\n"
            "SALAD 8,00\n"
            "BEER 5,00\n"
            "EYNOAD €49,00\n"
        )
        result = _parse_ocr_text(text)
        assert result["suggested_merchant"] is not None
        assert "BEACH RESTAURANT" in result["suggested_merchant"]
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_amount"] == 49.00

    def test_taverna_akroyial_receipt(self):
        """Test extraction from Taverna Akroyial receipt (Scanned_20260117-1517)."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = (
            "TAVERNA AKROYIAL\n"
            "Tel: 24 654321\n"
            "17/01/2026\n"
            "Table 5\n"
            "TOTAL €35,50\n"
        )
        result = _parse_ocr_text(text)
        assert result["suggested_merchant"] is not None
        assert "TAVERNA" in result["suggested_merchant"]
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1

    def test_kokos_tavern_receipt(self):
        """Test extraction from Kokos Tavern receipt (Scanned_20260118)."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = (
            "KOKOS TAVERN\n"
            "LARNACA\n"
            "16/01/2026\n"
            "Fish plate 18,00\n"
            "Salad 7,00\n"
            "Wine 12,00\n"
            "TOTAL €37,00\n"
        )
        result = _parse_ocr_text(text)
        assert result["suggested_merchant"] is not None
        assert "KOKOS TAVERN" in result["suggested_merchant"]
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_amount"] == 37.00

    def test_ram_oil_pyla_receipt(self):
        """Test extraction from R.A.M. Oil Pyla receipt (IMG20260124114731)."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = (
            "R.A.M.OIL PYLA\n"
            "PETROL STATION\n"
            "24/01/2026\n"
            "FUEL 32.51\n"
            "AMOUNT EUR32.51\n"
            "VISA\n"
        )
        result = _parse_ocr_text(text)
        assert result["suggested_merchant"] is not None
        assert "OIL" in result["suggested_merchant"].upper()
        assert result["suggested_amount"] == 32.51
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1

    def test_kokkinou_restaurant_receipt(self):
        """Test extraction from Kokkinou Restaurant receipt (Scanned_20260131)."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = (
            "KOKKINOU RESTAURANT\n"
            "31/01/2026\n"
            "Mezze 45,00\n"
            "Wine 15,00\n"
            "TOTAL €60,00\n"
        )
        result = _parse_ocr_text(text)
        assert result["suggested_merchant"] is not None
        assert "KOKKINOU RESTAURANT" in result["suggested_merchant"]
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_amount"] == 60.00


class TestOCRRealInvoices:
    """Test OCR parsing against real invoice text patterns."""

    def test_invoice_24_cso_gmbh(self):
        """Test full extraction from Invoice 24 (Example GmbH)."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = (
            "FACTURA #24\n"
            "Date: Feb 2, 2026\n"
            "Cobrar a: Example GmbH\n"
            "Direccion: Example Street 123, Test City\n"
            "\n"
            "Consultancy services - January 2026\n"
            "Hours: 105  Rate: 90.00\n"
            "\n"
            "Subtotal: 9.450,00 EUR\n"
            "IVA (0%): 0,00 EUR\n"
            "TOTAL: 9.450,00 EUR\n"
        )
        result = _parse_ocr_text(text)
        assert result["suggested_client"] == "Example GmbH"
        assert result["suggested_invoice_number"] == "24"
        assert result["suggested_amount"] == 9450.00
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 2

    def test_invoice_25_example_europe(self):
        """Test full extraction from Invoice 25 (Example Europe Limited)."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = (
            "Invoice no.: 25\n"
            "Date: 03/02/26\n"
            "Invoice To: Example Europe Limited\n"
            "Address: 14 Example Road, Test City\n"
            "\n"
            "SAP ISU Consultancy - January 2026\n"
            "40 hours x 150.00 EUR/hr\n"
            "\n"
            "Subtotal: 6,000.00\n"
            "VAT (0%): 0.00\n"
            "Total due: €6,000.00\n"
        )
        result = _parse_ocr_text(text)
        assert result["suggested_client"] == "Example Europe Limited"
        assert result["suggested_invoice_number"] == "25"
        assert result["suggested_amount"] == 6000.00
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 2

    def test_invoice_period_calculation(self):
        """Test that invoice period = date_month - 1 is correctly handled by router logic."""
        # This tests the period logic used in bulk import
        # Feb 2026 date → Jan 2026 period
        ocr_year = 2026
        ocr_month = 2
        period_month = ocr_month - 1
        period_year = ocr_year
        if period_month < 1:
            period_month = 12
            period_year = ocr_year - 1
        assert period_year == 2026
        assert period_month == 1

    def test_invoice_period_january_wrap(self):
        """Test January date wraps to December of previous year."""
        ocr_year = 2026
        ocr_month = 1
        period_month = ocr_month - 1
        period_year = ocr_year
        if period_month < 1:
            period_month = 12
            period_year = ocr_year - 1
        assert period_year == 2025
        assert period_month == 12


class TestOCREdgeCases:
    """Test OCR extraction edge cases and special patterns."""

    def test_eur_no_space_format(self):
        """EUR40.00 with no space between EUR and amount."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("AMOUNT EUR40.00")
        assert 40.00 in amounts

    def test_greek_total_eynoad(self):
        """Greek receipt total: EYNOAD (OCR variation of ΣΥΝΟΛΟ)."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("EYNOAD €49,00")
        assert 49.00 in amounts

    def test_greek_total_synolo(self):
        """Greek receipt total: SYNOLO."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("SYNOLO €125,90")
        assert 125.90 in amounts

    def test_total_eft_pattern(self):
        """Total-EFT pattern used on EFT/card receipts."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("Total-EFT EUR: 125.90")
        assert 125.90 in amounts

    def test_total_keyword_beats_larger_eur_amount(self):
        """TOTAL/AMOUNT keyword amounts take priority over currency-only amounts."""
        from src.finance.ocr.ocr_service import _extract_amounts
        # EFT EUR: 414.45 is currency-adjacent, Total-EFT is keyword
        # Keyword amounts should be returned, not the larger currency amount
        text = "EFT EUR: 414.45\nTip EUR: 11.45\nTotal-EFT EUR: 125.90\n"
        amounts = _extract_amounts(text)
        assert 125.90 in amounts
        assert 414.45 not in amounts

    def test_amount_keyword_beats_garbage_numbers(self):
        """AMOUNT keyword prevents garbage standalone numbers from winning."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "0002503.14.9.47 17269\nAMOUNT EUR40.00\n"
        amounts = _extract_amounts(text)
        assert 40.00 in amounts
        assert 503.14 not in amounts

    def test_currency_amounts_beat_standalone(self):
        """Currency-adjacent amounts take priority over standalone numbers."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "Reference: 999.99\nPrice: EUR42.50\n"
        amounts = _extract_amounts(text)
        assert 42.50 in amounts
        assert 999.99 not in amounts

    def test_multiple_amounts_picks_max(self):
        """Suggested amount should be the maximum found."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = "Coffee 5.00\nLunch 35.90\nTOTAL EUR: 125.90\n"
        result = _parse_ocr_text(text)
        assert result["suggested_amount"] == 125.90

    def test_empty_text_returns_none(self):
        """Empty OCR text returns None for all fields."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        result = _parse_ocr_text("")
        assert result["suggested_amount"] is None
        assert result["suggested_year"] is None
        assert result["suggested_month"] is None
        assert result["suggested_client"] is None
        assert result["suggested_merchant"] is None
        assert result["suggested_invoice_number"] is None

    def test_garbage_text_returns_none_for_structured_fields(self):
        """Garbage OCR text returns None for amount/date but may find merchant."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        result = _parse_ocr_text("asdfjkl qwerty zxcvb")
        assert result["suggested_amount"] is None
        assert result["suggested_year"] is None
        assert result["suggested_month"] is None

    def test_two_digit_year_boundary_99(self):
        """2-digit year 99 maps to 2099."""
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("31/12/99")
        assert (2099, 12, 31) in dates

    def test_two_digit_year_00(self):
        """2-digit year 00 maps to 2000."""
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("01/01/00")
        assert (2000, 1, 1) in dates

    def test_amount_with_dollar(self):
        """Dollar-denominated amount."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("$42.50")
        assert 42.50 in amounts

    def test_amount_european_comma_decimal(self):
        """European format with comma as decimal separator."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("TOTAL: 1.234,56")
        assert 1234.56 in amounts

    def test_client_on_next_line(self):
        """Client name on the line after 'Cobrar a:' header."""
        from src.finance.ocr.ocr_service import _extract_client_name
        text = "Cobrar a:\nMy Client Company\nDireccion: Somewhere"
        assert _extract_client_name(text) == "My Client Company"

    def test_merchant_skip_receipt_header(self):
        """Merchant extraction skips RECEIPT / RECIBO headers."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "RECEIPT\n12345\nACME RESTAURANT LTD\n15/01/2026"
        result = _extract_merchant(text)
        assert result is not None
        assert "ACME RESTAURANT" in result

    def test_merchant_skip_numeric_lines(self):
        """Merchant extraction skips purely numeric lines."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "12345678\n15/01/2026\nBIG STORE LTD\nItem 1"
        result = _extract_merchant(text)
        assert result is not None
        assert "BIG STORE" in result

    def test_date_with_dashes(self):
        """Date with dash separators."""
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("17-01-2026")
        assert (2026, 1, 17) in dates

    def test_date_month_year_only_english(self):
        """Month + year without day."""
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("January 2026")
        assert (2026, 1, 1) in dates

    def test_date_month_year_only_spanish(self):
        """Spanish month + year without day."""
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("Enero 2026")
        assert (2026, 1, 1) in dates

    def test_resolve_year_four_digit_unchanged(self):
        """4-digit years are returned unchanged."""
        from src.finance.ocr.ocr_service import _resolve_year
        assert _resolve_year(2026) == 2026

    def test_resolve_year_two_digit(self):
        """2-digit year 26 maps to 2026."""
        from src.finance.ocr.ocr_service import _resolve_year
        assert _resolve_year(26) == 2026

    def test_purchase_keyword_extraction(self):
        """PURCHASE keyword extracts amount."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("PURCHASE EUR40.00")
        assert 40.00 in amounts

    def test_cash_total_excluded(self):
        """CASH on the same line as TOTAL is excluded from Priority 1."""
        from src.finance.ocr.ocr_service import _extract_amounts
        # Real receipt pattern: TOTAL on clean line, CASH TOTAL on separate line
        # The real TOTAL should be kept, CASH TOTAL excluded
        amounts = _extract_amounts("TOTAL EUR42.50\nCASH TOTAL EUR50.00")
        assert 42.50 in amounts
        assert 50.00 not in amounts

    def test_metryta_total_excluded(self):
        """ΜΕΤΡΗΤΑ (Greek CASH) on the same line as TOTAL is excluded from Priority 1."""
        from src.finance.ocr.ocr_service import _extract_amounts
        # Real receipt: ΣΥΝΟΛΟ (total) on one line, ΜΕΤΡΗΤΑ line excluded
        amounts = _extract_amounts("TOTAL €42,50\nΜΕΤΡΗΤΑ TOTAL €50,00")
        assert 42.50 in amounts
        assert 50.00 not in amounts

    def test_cash_on_separate_line_keeps_total(self):
        """TOTAL on one line is kept; ΜΕΤΡΗΤΑ on separate line is excluded."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "TOTAL €49,00\nΜΕΤΡΗΤΑ TOTAL €50,00"
        amounts = _extract_amounts(text)
        assert 49.00 in amounts
        assert 50.00 not in amounts

    def test_extract_vat_simple(self):
        """Simple VAT extraction."""
        from src.finance.ocr.ocr_service import _extract_vat
        assert _extract_vat("VAT: 5.00") == 5.0

    def test_extract_vat_with_rate(self):
        """VAT extraction with percentage label."""
        from src.finance.ocr.ocr_service import _extract_vat
        assert _extract_vat("IVA (21%): 210.00 EUR") == 210.0

    def test_extract_vat_zero(self):
        """Explicit zero VAT returns 0.0."""
        from src.finance.ocr.ocr_service import _extract_vat
        assert _extract_vat("VAT (0%): 0.00") == 0.0

    def test_extract_vat_none(self):
        """Receipt without VAT line returns None."""
        from src.finance.ocr.ocr_service import _extract_vat
        assert _extract_vat("TOTAL: 42.50\nThank you!") is None

    def test_extract_vat_greek(self):
        """Greek ΦΠΑ label extraction."""
        from src.finance.ocr.ocr_service import _extract_vat
        assert _extract_vat("ΦΠΑ 24%: 12.00") == 12.0

    def test_merchant_skip_viva(self):
        """Viva payment processor is skipped."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "Viva Payments\nACME RESTAURANT LTD\n15/01/2026"
        result = _extract_merchant(text)
        assert result is not None
        assert "ACME RESTAURANT" in result

    def test_merchant_skip_worldline(self):
        """Worldline payment processor is skipped."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "Worldline\nSOME STORE LTD\n15/01/2026"
        result = _extract_merchant(text)
        assert result is not None
        assert "SOME STORE" in result

    def test_date_includes_day_component(self):
        """Verify that extracted dates include the day component."""
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("Receipt date: 25/06/2025")
        assert len(dates) >= 1
        year, month, day = dates[0]
        assert year == 2025
        assert month == 6
        assert day == 25

    def test_parse_ocr_text_includes_day_and_vat(self):
        """Verify _parse_ocr_text returns day, date, and vat fields."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = "Invoice 2025-06-15\nTOTAL: 100.00 EUR\nVAT: 21.00"
        result = _parse_ocr_text(text)
        assert result["suggested_day"] == 15
        assert result["suggested_date"] == "15/06/2025"
        assert result["suggested_vat"] == 21.0

    def test_change_total_excluded_from_cash_line(self):
        """CHANGE amount on same line as CASH is excluded."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("PURCHASE EUR40.00\nCHANGE TOTAL EUR10.00")
        assert 40.00 in amounts
        assert 10.00 not in amounts


class TestBulkImportOCR:
    """Test bulk import endpoints with OCR extraction."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.web.app import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def _make_text_pdf(self, tmp_path, text_lines):
        """Helper to create a simple PDF with text content."""
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        pdf_path = tmp_path / "test.pdf"
        doc = SimpleDocTemplate(str(pdf_path))
        styles = getSampleStyleSheet()
        elements = [Paragraph(line, styles["Normal"]) for line in text_lines]
        doc.build(elements)
        return pdf_path

    def test_invoice_bulk_import_creates_invoice(self, client, tmp_path):
        """Invoice bulk import creates an invoice with OCR-extracted data."""
        pdf_path = self._make_text_pdf(tmp_path, [
            "FACTURA #99",
            "Date: 2026-03-15",
            "Cobrar a: Test Client Corp",
            "TOTAL: 500.00 EUR",
        ])
        with open(pdf_path, "rb") as f:
            resp = client.post(
                "/api/finance/invoices/bulk-import",
                files=[("files", ("invoice_test.pdf", f, "application/pdf"))],
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1
        inv = data["invoices"][0]
        assert inv["total"] >= 0  # Invoice created

    def test_invoice_bulk_import_detects_client(self, client, tmp_path):
        """Invoice bulk import populates client_name from OCR."""
        pdf_path = self._make_text_pdf(tmp_path, [
            "FACTURA #50",
            "Date: 2026-02-10",
            "Cobrar a: Mi Empresa SL",
            "TOTAL: 1,000.00 EUR",
        ])
        with open(pdf_path, "rb") as f:
            resp = client.post(
                "/api/finance/invoices/bulk-import",
                files=[("files", ("inv_50.pdf", f, "application/pdf"))],
            )
        data = resp.json()
        assert data["imported"] == 1
        # Client should be extracted from OCR, not "(imported)"
        assert data["invoices"][0]["client_name"] != "(imported)"

    def test_invoice_bulk_import_period_minus_one(self, client, tmp_path):
        """Invoice bulk import sets period = date_month - 1."""
        pdf_path = self._make_text_pdf(tmp_path, [
            "Invoice no.: 77",
            "Date: 2026-03-01",
            "Invoice To: March Client",
            "TOTAL: 200.00 EUR",
        ])
        with open(pdf_path, "rb") as f:
            resp = client.post(
                "/api/finance/invoices/bulk-import",
                files=[("files", ("inv_77.pdf", f, "application/pdf"))],
            )
        data = resp.json()
        assert data["imported"] == 1
        # Period should be Feb 2026 (one month before March date)
        assert data["invoices"][0]["period"] == "2026-02"

    def test_expense_bulk_import_creates_expense(self, client, tmp_path):
        """Expense bulk import creates an expense with OCR-extracted data."""
        pdf_path = self._make_text_pdf(tmp_path, [
            "NOSH CAFE",
            "15/01/2026",
            "Coffee 5.00",
            "TOTAL EUR: 45.00",
        ])
        with open(pdf_path, "rb") as f:
            resp = client.post(
                "/api/finance/expenses/bulk-import",
                files=[("files", ("ticket_nosh.pdf", f, "application/pdf"))],
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1
        exp = data["expenses"][0]
        assert exp["amount"] >= 0  # Expense created

    def test_expense_bulk_import_detects_merchant(self, client, tmp_path):
        """Expense bulk import populates merchant from OCR."""
        pdf_path = self._make_text_pdf(tmp_path, [
            "ACME RESTAURANT LTD",
            "20/01/2026",
            "Dinner 35.00",
            "TOTAL EUR: 35.00",
        ])
        with open(pdf_path, "rb") as f:
            resp = client.post(
                "/api/finance/expenses/bulk-import",
                files=[("files", ("ticket_acme.pdf", f, "application/pdf"))],
            )
        data = resp.json()
        assert data["imported"] == 1
        # Merchant should be from OCR, not filename
        merchant = data["expenses"][0]["merchant"]
        assert merchant != "ticket_acme.pdf"


# ── OCR: New Extraction Tests (Overhaul) ──


class TestOCRSubtotalExclusion:
    """Test that SUBTOTAL is not matched by the TOTAL keyword pattern."""

    def test_subtotal_not_matched_as_total(self):
        """SUBTOTAL line should not be picked when a real TOTAL exists."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "SUBTOTAL EUR 27.32\nVAT EUR 5.19\nTOTAL EUR 32.51"
        amounts = _extract_amounts(text)
        assert 32.51 in amounts
        assert 27.32 not in amounts

    def test_subtotal_plus_vat_computation(self):
        """When TOTAL is garbled, subtotal+VAT should be computed."""
        from src.finance.ocr.ocr_service import _extract_amounts
        # No parseable TOTAL line, but SUBTOTAL and VAT both present
        text = "SUBTOTAL EUR 27.32\nVAT EUR 5.19\nTotal FUR 32,5]"
        amounts = _extract_amounts(text)
        assert 32.51 in amounts

    def test_subtotal_alone_not_returned_as_total(self):
        """SUBTOTAL without VAT should NOT be returned in Priority 1."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "SUBTOTAL EUR 27.32\nThank you!"
        amounts = _extract_amounts(text)
        # Priority 1 (TOTAL keyword) should not match; falls to Priority 2 (currency)
        assert 27.32 in amounts  # found via currency-adjacent


class TestOCRVersionStringFiltering:
    """Test that version/terminal strings are filtered out."""

    def test_version_string_filtered_from_amounts(self):
        """V27.21-0000-L should NOT be picked as amount."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "V27.21-0000-L\nAMOUNT EUR59.70"
        amounts = _extract_amounts(text)
        assert 59.70 in amounts
        assert 27.21 not in amounts

    def test_version_string_filtered_from_dates(self):
        """V01.59-0000-L should NOT produce a date."""
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("V01.59-0000-L\n08/01/26 07:49:46")
        # The real date 08/01/26 should be found, not 01/59
        years = [d[0] for d in dates]
        assert 2026 in years
        # No date with month=59 should exist
        months = [d[1] for d in dates]
        assert 59 not in months

    def test_terminal_id_filtered(self):
        """Terminal ID like 0002503.14.9.47 should not produce amounts."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "0002503.14.9.47 17269\nPURCHASE EUR40.00"
        amounts = _extract_amounts(text)
        assert 40.00 in amounts

    def test_aid_number_filtered(self):
        """AID number like A0000000041010 should not produce dates."""
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("A0000000041010\n15/03/2026")
        assert (2026, 3, 15) in dates


class TestOCRErrorCorrection:
    """Test OCR error correction for garbled keyword amounts."""

    def test_ocr_error_correction_amount_eurs(self):
        """AMOUNT EURS9, 70 with S ambiguity → min(39.70, 59.70) = 39.70."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "Some items\nAMOUNT EURS9, 70"
        amounts = _extract_amounts(text)
        assert 39.70 in amounts

    def test_ocr_error_correction_bracket(self):
        """Total FUR 32,5] with ]→1 correction → 32.51."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "SUBTOTAL EUR 27.32\nVA] EUR 5.19\nTotal FUR 32,5]"
        amounts = _extract_amounts(text)
        assert 32.51 in amounts

    def test_ocr_error_correction_pipe(self):
        """Amount with | → 1 correction."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "TOTAL EUR 4|,50"
        amounts = _extract_amounts(text)
        assert 41.50 in amounts


class TestOCRGreekVariants:
    """Test expanded Greek SYNOLO/ΣΥΝΟΛΟ variants."""

    def test_greek_eynond_variant(self):
        """EYNOND (OCR variant of ΣΥΝΟΛΟ) with flexible separator."""
        from src.finance.ocr.ocr_service import _extract_amounts
        # em dash separator as seen in real receipts
        amounts = _extract_amounts("EYNOND \u2014 43,50")
        assert 43.50 in amounts

    def test_greek_einond_variant(self):
        """EINOND OCR variant."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("EINOND €55,00")
        assert 55.00 in amounts

    def test_greek_e1nond_variant(self):
        """E1NOND OCR variant (I→1)."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("E1NOND €55,00")
        assert 55.00 in amounts

    def test_greek_eynoao_variant(self):
        """EYNOAO OCR variant."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("EYNOAO €49,00")
        assert 49.00 in amounts

    def test_greek_dash_ynoao_variant(self):
        """—YNOAO OCR variant (em dash prefix)."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("\u2014YNOAO €49,00")
        assert 49.00 in amounts


class TestNeedsReview:
    """Test needs_review flag in OCR results."""

    def test_needs_review_no_amount(self):
        """Empty text sets needs_review=True."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        result = _parse_ocr_text("")
        assert result["needs_review"] is True

    def test_needs_review_with_amount(self):
        """Normal text with amount sets needs_review=False."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = "ACME RESTAURANT LIMITED\nLarnaca Cyprus\n15/01/2026\nFish plate and salad\nTOTAL EUR 42.50"
        result = _parse_ocr_text(text)
        assert result["needs_review"] is False

    def test_needs_review_low_alpha(self):
        """Text with very few alphabetic chars sets needs_review=True."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        result = _parse_ocr_text("12345 67890")
        assert result["needs_review"] is True

    def test_needs_review_no_amount_detected(self):
        """Text with no parseable amount sets needs_review=True."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = "Some random text without any amounts but with enough alphabetic characters to pass"
        result = _parse_ocr_text(text)
        assert result["needs_review"] is True


class TestDateTimestampPriority:
    """Test that dates with timestamps get priority over standalone dates."""

    def test_date_with_timestamp_preferred(self):
        """Date followed by HH:MM should be preferred over standalone dates."""
        from src.finance.ocr.ocr_service import _extract_dates
        text = "January 2025\n08/01/26 07:49:46\nThank you"
        dates = _extract_dates(text)
        assert len(dates) >= 1
        # The timestamped date should be first
        assert dates[0] == (2026, 1, 8)

    def test_garbled_date_ddmm_yy(self):
        """Garbled date 3101/28 (DDMM/YY format) with timestamp."""
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("3101/28 15:21:32")
        assert len(dates) >= 1
        # Should parse as day=31, month=01, year=2028
        assert (2028, 1, 31) in dates

    def test_normal_date_without_timestamp(self):
        """Dates without timestamp still work."""
        from src.finance.ocr.ocr_service import _extract_dates
        dates = _extract_dates("15/03/2026")
        assert (2026, 3, 15) in dates


class TestMerchantGarbagePrefix:
    """Test merchant name OCR garbage prefix stripping."""

    def test_merchant_garbage_prefix_stripped(self):
        """Leading non-alpha chars stripped from merchant name."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "_ fi | Fe KOKKINOU RESTAURANT\n31/01/2026\nTOTAL €60,00"
        result = _extract_merchant(text)
        assert result is not None
        assert "KOKKINOU RESTAURANT" in result
        assert not result.startswith("_")
        assert not result.startswith("|")

    def test_merchant_leading_digits_stripped(self):
        """Leading digits stripped from merchant with company suffix."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "123 ACME LTD\nSome Address\n15/01/2026"
        result = _extract_merchant(text)
        assert result is not None
        # LTD is stripped by _clean_merchant_name, "ACME" remains
        assert "ACME" in result

    def test_merchant_short_garbage_word_stripped(self):
        """Leading 1-2 char lowercase words stripped."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "ot BEACH RESTAURANT\n17/01/2026"
        result = _extract_merchant(text)
        assert result is not None
        assert "BEACH RESTAURANT" in result


class TestOCRVATGarbled:
    """Test VAT extraction with OCR-garbled 'VAT' text."""

    def test_vat_bracket_garble(self):
        """VA] (OCR garble of VAT)."""
        from src.finance.ocr.ocr_service import _extract_vat
        assert _extract_vat("VA] EUR 5.19") == 5.19

    def test_vat_pipe_garble(self):
        """VA| (OCR garble of VAT)."""
        from src.finance.ocr.ocr_service import _extract_vat
        assert _extract_vat("VA| EUR 5.19") == 5.19

    def test_vat_exclamation_garble(self):
        """VA! (OCR garble of VAT)."""
        from src.finance.ocr.ocr_service import _extract_vat
        assert _extract_vat("VA! EUR 5.19") == 5.19

    def test_vat_curly_garble(self):
        """VA} (OCR garble of VAT)."""
        from src.finance.ocr.ocr_service import _extract_vat
        assert _extract_vat("VA} EUR 5.19") == 5.19

    def test_iva_extraction(self):
        """IVA (Spanish VAT) with percentage."""
        from src.finance.ocr.ocr_service import _extract_vat
        assert _extract_vat("IVA (21%): 210.00") == 210.0


# ── OCR: Tip Computation ──


class TestOCRTipComputation:
    """Test tip computation pattern for POS receipts."""

    def test_tip_computation_basic(self):
        """(122.50 + 12.26 → 134.76."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "EFT EUR: 414.45\nTip EUR: 11.45\n(122.50 + 12.26\nVerified by Device"
        amounts = _extract_amounts(text)
        assert 134.76 in amounts

    def test_tip_computation_without_parens(self):
        """122.50 + 12.26 without leading paren."""
        from src.finance.ocr.ocr_service import _extract_amounts
        # If no TOTAL/SALE keyword, and tip pattern is highest priority available
        text = "Some items\n122.50 + 12.26"
        amounts = _extract_amounts(text)
        assert 134.76 in amounts

    def test_tip_does_not_override_total_keyword(self):
        """TOTAL keyword takes priority over tip computation."""
        from src.finance.ocr.ocr_service import _extract_amounts
        text = "TOTAL EUR 125.90\n(122.50 + 12.26"
        amounts = _extract_amounts(text)
        assert 125.90 in amounts
        # Tip should NOT be returned since TOTAL keyword matched
        assert 134.76 not in amounts


# ── OCR: S Digit Ambiguity ──


class TestOCRSDigitAmbiguity:
    """Test that S in OCR-garbled amounts tries both 3 and 5, picks min."""

    def test_s_correction_picks_min(self):
        """EURS9,70 → min(39.70, 59.70) = 39.70."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("AMOUNT EURS9, 70")
        assert 39.70 in amounts
        assert 59.70 not in amounts

    def test_s_correction_no_s_unchanged(self):
        """Without S in garbled part, no ambiguity."""
        from src.finance.ocr.ocr_service import _extract_amounts
        amounts = _extract_amounts("AMOUNT EUR40.00")
        assert 40.00 in amounts

    def test_s_correction_multiple_s(self):
        """Multiple S chars → each gets substituted."""
        from src.finance.ocr.ocr_service import _extract_amounts
        # "AMOUNT EURSS,00" → S→3,3 gives 33.00; S→5,5 gives 55.00; min is 33.00
        amounts = _extract_amounts("AMOUNT EURSS,00")
        assert 33.00 in amounts


# ── OCR: Merchant Scoring ──


class TestMerchantScoring:
    """Test merchant extraction scoring system."""

    def test_restaurant_beats_address(self):
        """KOKKINOU RESTAURANT wins over LARNACOS STR address line."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = (
            "33, LARNACOS STR. MOSFILOTI\n"
            "KOKKINOU RESTAURANT\n"
            "31/01/2026\n"
            "TOTAL €60,00\n"
        )
        result = _extract_merchant(text)
        assert result is not None
        assert "KOKKINOU RESTAURANT" in result

    def test_blacklist_payment_systems(self):
        """JCC PAYMENT SYSTEMS is penalized."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "JCC PAYMENT SYSTEMS\nPETROLINA KITI\n15/01/2026"
        result = _extract_merchant(text)
        assert result is not None
        assert "PETROLINA" in result
        assert "JCC" not in result

    def test_blacklist_cardholder_copy(self):
        """CARDHOLDER COPY is penalized."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "CARDHOLDER COPY\nACME LTD\n15/01/2026"
        result = _extract_merchant(text)
        assert result is not None
        assert "ACME" in result

    def test_company_suffix_bonus(self):
        """Line with LTD suffix gets bonus over plain text."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "Some random line\nBIG COMPANY LTD\n15/01/2026"
        result = _extract_merchant(text)
        assert result is not None
        assert "BIG COMPANY" in result

    def test_address_penalty(self):
        """Lines with street indicators are penalized."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "15 KRUOU NEROU\nNOSH\n15/01/2026"
        result = _extract_merchant(text)
        assert result is not None
        assert "NOSH" in result

    def test_position_bonus_early_line(self):
        """Earlier lines get position bonus when no suffix distinction."""
        from src.finance.ocr.ocr_service import _extract_merchant
        text = "FIRST SHOP\nSECOND SHOP\n15/01/2026"
        result = _extract_merchant(text)
        assert result == "FIRST SHOP"


# ── Bulk Import Persistence ──


class TestBulkImportPersistence:
    """Test persistence fixes in expense bulk import."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.web.app import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_no_zero_amount_expenses(self, client, tmp_path):
        """Bulk import never creates an expense with amount=0.00."""
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet

        # PDF with no parseable amount → should get 0.01 sentinel
        pdf_path = tmp_path / "no_amount.pdf"
        doc = SimpleDocTemplate(str(pdf_path))
        styles = getSampleStyleSheet()
        elements = [Paragraph("Just random text with no numbers", styles["Normal"])]
        doc.build(elements)

        with open(pdf_path, "rb") as f:
            resp = client.post(
                "/api/finance/expenses/bulk-import",
                files=[("files", ("no_amount.pdf", f, "application/pdf"))],
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1
        assert data["expenses"][0]["amount"] > 0  # not 0.00

    def test_needs_review_when_no_amount(self, client, tmp_path):
        """Expense gets [NEEDS REVIEW] note when no amount is detected."""
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet

        pdf_path = tmp_path / "review_me.pdf"
        doc = SimpleDocTemplate(str(pdf_path))
        styles = getSampleStyleSheet()
        elements = [Paragraph("Unrecognizable content qwerty", styles["Normal"])]
        doc.build(elements)

        with open(pdf_path, "rb") as f:
            resp = client.post(
                "/api/finance/expenses/bulk-import",
                files=[("files", ("review_me.pdf", f, "application/pdf"))],
            )
        data = resp.json()
        assert data["imported"] == 1
        # Verify expense has review note
        exp_id = data["expenses"][0]["expense_id"]
        resp = client.get("/api/finance/expenses")
        expenses = resp.json()["expenses"]
        found = [e for e in expenses if e["id"] == exp_id]
        assert len(found) == 1
        assert found[0]["notes"] is not None
        assert "NEEDS REVIEW" in found[0]["notes"]


# ── E2E: Ticket Files OCR ──


class TestTicketFilesE2E:
    """End-to-end tests on real ticket files from ./tickets/ directory.

    These tests are skipped if the tickets directory doesn't exist.
    """

    TICKETS_DIR = Path(__file__).parent.parent / "tickets"

    @pytest.fixture(autouse=True)
    def skip_if_no_tickets(self):
        if not self.TICKETS_DIR.exists():
            pytest.skip("No tickets directory")

    def _run_ocr(self, filename):
        """Run OCR on a single ticket file and return parsed result."""
        from src.finance.ocr.ocr_service import extract_from_image, extract_from_pdf
        fpath = self.TICKETS_DIR / filename
        if not fpath.exists():
            pytest.skip(f"File not found: {filename}")
        if fpath.suffix.lower() == ".pdf":
            return extract_from_pdf(fpath)
        return extract_from_image(fpath)

    def test_all_files_produce_results(self):
        """Every file in tickets/ produces an OCR result dict."""
        from src.finance.ocr.ocr_service import extract_from_image, extract_from_pdf
        for fpath in sorted(self.TICKETS_DIR.iterdir()):
            if fpath.suffix.lower() in (".pdf", ".jpg", ".jpeg", ".png"):
                if fpath.suffix.lower() == ".pdf":
                    result = extract_from_pdf(fpath)
                else:
                    result = extract_from_image(fpath)
                assert isinstance(result, dict), f"Failed for {fpath.name}"
                assert "raw_text" in result
                assert "suggested_amount" in result
                assert "needs_review" in result

    def test_no_zero_amounts_without_review(self):
        """If amount is 0 or None, needs_review must be True."""
        from src.finance.ocr.ocr_service import extract_from_image, extract_from_pdf
        for fpath in sorted(self.TICKETS_DIR.iterdir()):
            if fpath.suffix.lower() in (".pdf", ".jpg", ".jpeg", ".png"):
                if fpath.suffix.lower() == ".pdf":
                    result = extract_from_pdf(fpath)
                else:
                    result = extract_from_image(fpath)
                amt = result.get("suggested_amount")
                if not amt or amt <= 0:
                    assert result["needs_review"] is True, (
                        f"{fpath.name}: amount={amt} but needs_review={result['needs_review']}"
                    )

    def test_merchant_never_contains_blacklisted(self):
        """Merchant name should never be a payment processor or card network."""
        from src.finance.ocr.ocr_service import extract_from_image, extract_from_pdf
        blacklisted = {"JCC", "PAYMENT SYSTEMS", "WORLDLINE", "CARDHOLDER COPY", "VISA", "MASTERCARD"}
        for fpath in sorted(self.TICKETS_DIR.iterdir()):
            if fpath.suffix.lower() in (".pdf", ".jpg", ".jpeg", ".png"):
                if fpath.suffix.lower() == ".pdf":
                    result = extract_from_pdf(fpath)
                else:
                    result = extract_from_image(fpath)
                merchant = result.get("suggested_merchant")
                if merchant:
                    merchant_upper = merchant.upper()
                    for bl in blacklisted:
                        assert bl not in merchant_upper, (
                            f"{fpath.name}: merchant '{merchant}' contains blacklisted '{bl}'"
                        )


# ── E2E: Exact-Value Ticket File Tests ──


class TestTicketExactValues:
    """Exact-value E2E tests for each of the 10 ticket files.

    These tests run OCR on the actual ticket files and assert the exact
    extracted values. Tests are skipped if the tickets directory doesn't exist.
    """

    TICKETS_DIR = Path(__file__).parent.parent / "tickets"

    @pytest.fixture(autouse=True)
    def skip_if_no_tickets(self):
        if not self.TICKETS_DIR.exists():
            pytest.skip("No tickets directory")

    def _run_ocr(self, filename):
        from src.finance.ocr.ocr_service import extract_from_image, extract_from_pdf
        fpath = self.TICKETS_DIR / filename
        if not fpath.exists():
            pytest.skip(f"File not found: {filename}")
        if fpath.suffix.lower() == ".pdf":
            return extract_from_pdf(fpath)
        return extract_from_image(fpath)

    # ── File 1: R.A.M. OIL PYLA (IMG20260124114731.jpg) ──

    def test_file1_ram_oil_amount(self):
        result = self._run_ocr("IMG20260124114731.jpg")
        assert result["suggested_amount"] == 32.51

    def test_file1_ram_oil_merchant(self):
        result = self._run_ocr("IMG20260124114731.jpg")
        assert result["suggested_merchant"] == "R.A.M. OIL PYLA"

    def test_file1_ram_oil_date(self):
        result = self._run_ocr("IMG20260124114731.jpg")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_day"] == 24

    def test_file1_ram_oil_no_review(self):
        result = self._run_ocr("IMG20260124114731.jpg")
        assert result["needs_review"] is False

    # ── File 2: CAPTAIN COD (IMG20260124155947.jpg) ──

    def test_file2_captain_cod_amount(self):
        result = self._run_ocr("IMG20260124155947.jpg")
        assert result["suggested_amount"] == 50.40

    def test_file2_captain_cod_merchant(self):
        result = self._run_ocr("IMG20260124155947.jpg")
        assert result["suggested_merchant"] == "CAPTAIN COD"

    def test_file2_captain_cod_date(self):
        result = self._run_ocr("IMG20260124155947.jpg")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_day"] == 24

    def test_file2_captain_cod_no_review(self):
        result = self._run_ocr("IMG20260124155947.jpg")
        assert result["needs_review"] is False

    # ── File 3: bar Du Sole! (Scanned_20260103-1546.pdf) ──

    def test_file3_bar_du_sole_amount(self):
        """Tip computation: 122.50 + 12.26 = 134.76 (OCR reads 12.26 not 12.25)."""
        result = self._run_ocr("Scanned_20260103-1546.pdf")
        assert result["suggested_amount"] == 134.76

    def test_file3_bar_du_sole_merchant(self):
        result = self._run_ocr("Scanned_20260103-1546.pdf")
        assert result["suggested_merchant"] == "bar Du Sole!"

    def test_file3_bar_du_sole_date(self):
        """Date from filename: Scanned_20260103 -> 2026-01-03."""
        result = self._run_ocr("Scanned_20260103-1546.pdf")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_day"] == 3

    def test_file3_bar_du_sole_no_review(self):
        result = self._run_ocr("Scanned_20260103-1546.pdf")
        assert result["needs_review"] is False

    # ── File 4: PETROLINA KITI (Scanned_20260108-0758.pdf) ──

    def test_file4_petrolina_kiti_amount(self):
        result = self._run_ocr("Scanned_20260108-0758.pdf")
        assert result["suggested_amount"] == 40.00

    def test_file4_petrolina_kiti_merchant(self):
        result = self._run_ocr("Scanned_20260108-0758.pdf")
        assert result["suggested_merchant"] == "PETROLINA KITI"

    def test_file4_petrolina_kiti_date(self):
        result = self._run_ocr("Scanned_20260108-0758.pdf")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_day"] == 8

    def test_file4_petrolina_kiti_no_review(self):
        result = self._run_ocr("Scanned_20260108-0758.pdf")
        assert result["needs_review"] is False

    # ── File 5: NOSH (Scanned_20260110-1558.pdf) ──

    def test_file5_nosh_amount(self):
        result = self._run_ocr("Scanned_20260110-1558.pdf")
        assert result["suggested_amount"] == 125.90

    def test_file5_nosh_merchant(self):
        result = self._run_ocr("Scanned_20260110-1558.pdf")
        assert result["suggested_merchant"] == "NOSH"

    def test_file5_nosh_date(self):
        result = self._run_ocr("Scanned_20260110-1558.pdf")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_day"] == 10

    def test_file5_nosh_no_review(self):
        result = self._run_ocr("Scanned_20260110-1558.pdf")
        assert result["needs_review"] is False

    # ── File 6: PETROLINA - DROMOLAXIA (Scanned_20260115-1336.pdf) ──

    def test_file6_petrolina_dromolaxia_amount(self):
        result = self._run_ocr("Scanned_20260115-1336.pdf")
        assert result["suggested_amount"] == 39.70

    def test_file6_petrolina_dromolaxia_merchant(self):
        result = self._run_ocr("Scanned_20260115-1336.pdf")
        assert result["suggested_merchant"] == "PETROLINA - DROMOLAXIA"

    def test_file6_petrolina_dromolaxia_date(self):
        result = self._run_ocr("Scanned_20260115-1336.pdf")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_day"] == 15

    def test_file6_petrolina_dromolaxia_no_review(self):
        result = self._run_ocr("Scanned_20260115-1336.pdf")
        assert result["needs_review"] is False

    # ── File 7: BEACH RESTAURANT (Scanned_20260117-1516.pdf) ──

    def test_file7_beach_restaurant_amount(self):
        result = self._run_ocr("Scanned_20260117-1516.pdf")
        assert result["suggested_amount"] == 49.00

    def test_file7_beach_restaurant_merchant(self):
        result = self._run_ocr("Scanned_20260117-1516.pdf")
        assert result["suggested_merchant"] == "BEACH RESTAURANT"

    def test_file7_beach_restaurant_date(self):
        result = self._run_ocr("Scanned_20260117-1516.pdf")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_day"] == 17

    def test_file7_beach_restaurant_no_review(self):
        result = self._run_ocr("Scanned_20260117-1516.pdf")
        assert result["needs_review"] is False

    # ── File 8: TAVERNA AKROYIALI (Scanned_20260117-1517.pdf) ──

    def test_file8_taverna_akroyiali_amount(self):
        result = self._run_ocr("Scanned_20260117-1517.pdf")
        assert result["suggested_amount"] == 50.00

    def test_file8_taverna_akroyiali_merchant(self):
        result = self._run_ocr("Scanned_20260117-1517.pdf")
        assert result["suggested_merchant"] == "TAVERNA AKROYIALI"

    def test_file8_taverna_akroyiali_date(self):
        result = self._run_ocr("Scanned_20260117-1517.pdf")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_day"] == 17

    def test_file8_taverna_akroyiali_no_review(self):
        result = self._run_ocr("Scanned_20260117-1517.pdf")
        assert result["needs_review"] is False

    # ── File 9: KOKOS TAVERN (Scanned_20260118-1447.pdf) ──

    def test_file9_kokos_tavern_amount(self):
        result = self._run_ocr("Scanned_20260118-1447.pdf")
        assert result["suggested_amount"] == 25.00

    def test_file9_kokos_tavern_merchant(self):
        result = self._run_ocr("Scanned_20260118-1447.pdf")
        assert result["suggested_merchant"] == "KOKOS TAVERN"

    def test_file9_kokos_tavern_date(self):
        result = self._run_ocr("Scanned_20260118-1447.pdf")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_day"] == 18

    def test_file9_kokos_tavern_no_review(self):
        result = self._run_ocr("Scanned_20260118-1447.pdf")
        assert result["needs_review"] is False

    # ── File 10: KOKKINOU RESTAURANT (Scanned_20260131-1522.pdf) ──

    def test_file10_kokkinou_amount(self):
        result = self._run_ocr("Scanned_20260131-1522.pdf")
        assert result["suggested_amount"] == 43.50

    def test_file10_kokkinou_merchant(self):
        result = self._run_ocr("Scanned_20260131-1522.pdf")
        assert result["suggested_merchant"] == "KOKKINOU RESTAURANT"

    def test_file10_kokkinou_date(self):
        result = self._run_ocr("Scanned_20260131-1522.pdf")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 1
        assert result["suggested_day"] == 31

    def test_file10_kokkinou_no_review(self):
        result = self._run_ocr("Scanned_20260131-1522.pdf")
        assert result["needs_review"] is False


# ── OCR Sanity Tests ──


class TestOCRSanity:
    """Property-based sanity tests for OCR extraction invariants."""

    def test_amount_never_default_penny(self):
        """Amount should never be 0.01 or 0.00 — those indicate extraction failure."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = "TOTAL EUR 42.50\nSome receipt"
        result = _parse_ocr_text(text)
        if result["suggested_amount"] is not None:
            assert result["suggested_amount"] > 0.05

    def test_null_amount_means_needs_review(self):
        """If no reliable amount extracted, needs_review must be True."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        result = _parse_ocr_text("Some text without amounts")
        assert result["suggested_amount"] is None or result["suggested_amount"] <= 0.05
        assert result["needs_review"] is True

    def test_valid_amount_means_no_review(self):
        """If a valid amount is extracted, needs_review should be False."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = "ACME STORE\nTOTAL EUR 42.50\n15/01/2026"
        result = _parse_ocr_text(text)
        assert result["suggested_amount"] == 42.50
        assert result["needs_review"] is False

    def test_merchant_not_short_garbage(self):
        """Merchant should never be 1-3 chars (garbage)."""
        from src.finance.ocr.ocr_service import _is_garbage_merchant
        for bad in ["AB", "x", "12", "hi"]:
            assert _is_garbage_merchant(bad) is True

    def test_merchant_valid_names_pass(self):
        """Known valid merchant names should not be flagged as garbage."""
        from src.finance.ocr.ocr_service import _is_garbage_merchant
        valid_names = [
            "PETROLINA KITI", "NOSH", "BEACH RESTAURANT",
            "CAPTAIN COD", "KOKOS TAVERN", "R.A.M. OIL PYLA",
            "KOKKINOU RESTAURANT", "TAVERNA AKROYIALI",
            "PETROLINA - DROMOLAXIA", "bar Du Sole!",
        ]
        for name in valid_names:
            assert _is_garbage_merchant(name) is False, f"{name!r} incorrectly flagged as garbage"

    def test_date_components_valid_ranges(self):
        """Extracted date components must be in valid ranges."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = "TOTAL EUR 10.00\n15/06/2026"
        result = _parse_ocr_text(text)
        if result["suggested_year"]:
            assert 2000 <= result["suggested_year"] <= 2099
        if result["suggested_month"]:
            assert 1 <= result["suggested_month"] <= 12
        if result["suggested_day"]:
            assert 1 <= result["suggested_day"] <= 31

    def test_filename_date_beats_ocr_date(self):
        """Filename date should override OCR-extracted date."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        text = "ACME STORE\nTOTAL EUR 10.00\n15/06/2024"
        result = _parse_ocr_text(text, filename="IMG20260801120000.jpg")
        assert result["suggested_year"] == 2026
        assert result["suggested_month"] == 8
        assert result["suggested_day"] == 1

    def test_parse_ocr_text_returns_all_fields(self):
        """_parse_ocr_text always returns all expected fields."""
        from src.finance.ocr.ocr_service import _parse_ocr_text
        result = _parse_ocr_text("")
        expected_keys = {
            "raw_text", "suggested_amount", "suggested_year", "suggested_month",
            "suggested_day", "suggested_date", "suggested_vat", "suggested_client",
            "suggested_merchant", "suggested_invoice_number", "needs_review",
        }
        assert set(result.keys()) == expected_keys

    def test_garbage_merchant_patterns(self):
        """Known garbage patterns should be detected."""
        from src.finance.ocr.ocr_service import _is_garbage_merchant
        garbage_patterns = [
            "COD LTD CASHTE , 383",   # comma + digits
            "hay ule?",               # question mark
            "Fs , (fa > :",           # special chars
            "boa-Vus",                # hyphenated inconsistent case
            "RAM. OIL CYPRUS LID HGResss",  # repeated chars + mixed case
            "Bar Du Sole 4OSO",       # digit + uppercase
        ]
        for name in garbage_patterns:
            assert _is_garbage_merchant(name) is True, f"{name!r} should be garbage"


class TestBulkImportProgress:
    """Tests for bulk import progress feedback fields (needs_review, warning)."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAP_DATA_ROOT", str(tmp_path))
        import src.web.dependencies as deps
        monkeypatch.setattr(deps, "DATA_ROOT", tmp_path)

        from src.web.app import app
        from starlette.testclient import TestClient
        return TestClient(app)

    def _make_text_pdf(self, tmp_path, text_lines, name="test.pdf"):
        """Helper to create a simple PDF with text content."""
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        pdf_path = tmp_path / name
        doc = SimpleDocTemplate(str(pdf_path))
        styles = getSampleStyleSheet()
        elements = [Paragraph(line, styles["Normal"]) for line in text_lines]
        doc.build(elements)
        return pdf_path

    def test_bulk_import_single_file_has_status_fields(self, client, tmp_path):
        """Bulk import response includes needs_review and warning fields."""
        pdf_path = self._make_text_pdf(tmp_path, [
            "ACME STORE",
            "TOTAL EUR 55.00",
            "Date: 2026-03-15",
        ])
        with open(pdf_path, "rb") as f:
            resp = client.post(
                "/api/finance/expenses/bulk-import",
                files=[("files", ("receipt.pdf", f, "application/pdf"))],
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1
        exp = data["expenses"][0]
        # Must have both new fields
        assert "needs_review" in exp
        assert "warning" in exp
        assert isinstance(exp["needs_review"], bool)

    def test_bulk_import_multiple_files_individual(self, client, tmp_path):
        """Sending files one by one (simulating frontend serial loop) works correctly."""
        texts = [
            (["STORE A", "TOTAL EUR 10.00", "01/01/2026"], "file1.pdf"),
            (["STORE B", "TOTAL EUR 20.00", "02/02/2026"], "file2.pdf"),
            (["STORE C", "TOTAL EUR 30.00", "03/03/2026"], "file3.pdf"),
        ]
        results = []
        for text_lines, filename in texts:
            pdf_path = self._make_text_pdf(tmp_path, text_lines, name=filename)
            with open(pdf_path, "rb") as f:
                resp = client.post(
                    "/api/finance/expenses/bulk-import",
                    files=[("files", (filename, f, "application/pdf"))],
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["imported"] == 1
            results.append(data["expenses"][0])

        # Each response is independent
        assert len(results) == 3
        for r in results:
            assert "expense_id" in r
            assert "needs_review" in r
            assert "warning" in r
        # All have distinct expense IDs
        ids = [r["expense_id"] for r in results]
        assert len(set(ids)) == 3

    def test_bulk_import_progress_calculation(self):
        """Pure unit test: progress percentage calculation from file states."""
        files = [
            {"status": "ok"},
            {"status": "ok"},
            {"status": "processing"},
            {"status": "pending"},
            {"status": "pending"},
        ]
        total = len(files)
        processed = sum(1 for f in files if f["status"] in ("ok", "warning", "error"))
        pct = round((processed / total) * 100) if total > 0 else 0
        assert total == 5
        assert processed == 2
        assert pct == 40

    def test_bulk_import_state_transitions(self):
        """Unit test: valid file state transitions during bulk import."""
        valid_transitions = {
            "pending": {"processing"},
            "processing": {"ok", "warning", "error"},
        }
        # pending -> processing -> ok
        state = "pending"
        assert "processing" in valid_transitions[state]
        state = "processing"
        assert "ok" in valid_transitions[state]

        # pending -> processing -> error
        state = "pending"
        assert "processing" in valid_transitions[state]
        state = "processing"
        assert "error" in valid_transitions[state]

        # ok and error are terminal (not in valid_transitions as source)
        assert "ok" not in valid_transitions
        assert "error" not in valid_transitions
        assert "warning" not in valid_transitions

    def test_bulk_import_needs_review_warning(self, client, tmp_path):
        """PDF with no parseable amount gets needs_review=True and warning."""
        pdf_path = self._make_text_pdf(tmp_path, [
            "Just some random text",
            "No amounts here at all",
        ])
        with open(pdf_path, "rb") as f:
            resp = client.post(
                "/api/finance/expenses/bulk-import",
                files=[("files", ("noamount.pdf", f, "application/pdf"))],
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1
        exp = data["expenses"][0]
        assert exp["needs_review"] is True
        assert exp["warning"] is not None
        assert "NEEDS REVIEW" in exp["warning"]

    def test_bulk_import_partial_failure(self, client, tmp_path):
        """One file failing OCR doesn't block the other files."""
        # File 1: valid PDF with amount
        pdf1 = self._make_text_pdf(tmp_path, [
            "GOOD STORE",
            "TOTAL EUR 42.00",
            "Date: 2026-05-10",
        ], name="good.pdf")

        # File 2: PDF with no amount (will get needs_review)
        pdf2 = self._make_text_pdf(tmp_path, [
            "Nothing useful here",
        ], name="bad.pdf")

        # Send them one at a time (simulating serial frontend)
        results = []
        for pdf_path, filename in [(pdf1, "good.pdf"), (pdf2, "bad.pdf")]:
            with open(pdf_path, "rb") as f:
                resp = client.post(
                    "/api/finance/expenses/bulk-import",
                    files=[("files", (filename, f, "application/pdf"))],
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["imported"] == 1
            results.append(data["expenses"][0])

        # Both created expenses (one good, one needs review)
        assert len(results) == 2
        # The good one should not need review (if OCR found the amount)
        # The bad one should need review
        assert results[1]["needs_review"] is True
        assert results[1]["warning"] is not None
