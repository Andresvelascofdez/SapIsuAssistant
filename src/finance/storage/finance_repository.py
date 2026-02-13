"""Finance repository - all DB operations for the personal finance module."""
import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_CATEGORIES = [
    "Servicios profesionales",
    "Software y hosting",
    "Material de oficina",
    "Otros",
]


@dataclass
class FinanceSettings:
    id: int
    tax_rate_default: float
    company_name: str
    company_address: str
    company_tax_id: str | None
    company_email: str | None
    company_phone: str | None
    company_bank_details: str | None
    updated_at: str


@dataclass
class ExpenseCategory:
    id: int
    name: str
    is_active: bool
    sort_order: int


@dataclass
class Document:
    id: str
    original_file_name: str
    mime_type: str
    size_bytes: int
    storage_path: str
    sha256: str | None
    ocr_raw_text: str | None
    ocr_detected_amount: float | None
    ocr_detected_date_iso: str | None
    created_at: str


@dataclass
class Expense:
    id: str
    period_year: int
    period_month: int
    category_id: int
    category_name: str
    merchant: str | None
    amount: float
    currency: str
    notes: str | None
    document_id: str | None
    document_not_required: bool
    created_at: str
    updated_at: str


@dataclass
class Invoice:
    id: str
    period_year: int
    period_month: int
    client_name: str
    client_address: str | None
    invoice_number: str
    status: str
    currency: str
    vat_rate: float
    subtotal: float
    vat_amount: float
    total: float
    notes: str | None
    document_id: str | None
    created_at: str
    updated_at: str


@dataclass
class InvoiceItem:
    id: str
    invoice_id: str
    description: str
    quantity: float
    unit: str
    unit_price: float
    line_total: float


def _round2(v: float) -> float:
    return round(v, 2)


class FinanceRepository:
    """Repository for all finance DB operations. Uses a single SQLite file."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS finance_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tax_rate_default REAL NOT NULL DEFAULT 0.15,
                    company_name TEXT NOT NULL DEFAULT '',
                    company_address TEXT NOT NULL DEFAULT '',
                    company_tax_id TEXT,
                    company_email TEXT,
                    company_phone TEXT,
                    company_bank_details TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expense_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    original_file_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    storage_path TEXT NOT NULL,
                    sha256 TEXT,
                    ocr_raw_text TEXT,
                    ocr_detected_amount REAL,
                    ocr_detected_date_iso TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id TEXT PRIMARY KEY,
                    period_year INTEGER NOT NULL,
                    period_month INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    merchant TEXT,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'EUR',
                    notes TEXT,
                    document_id TEXT,
                    document_not_required INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (category_id) REFERENCES expense_categories(id),
                    FOREIGN KEY (document_id) REFERENCES documents(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expenses_period
                ON expenses(period_year, period_month)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY,
                    period_year INTEGER NOT NULL,
                    period_month INTEGER NOT NULL,
                    client_name TEXT NOT NULL,
                    client_address TEXT,
                    invoice_number TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    currency TEXT NOT NULL DEFAULT 'EUR',
                    vat_rate REAL NOT NULL DEFAULT 0.0,
                    subtotal REAL NOT NULL DEFAULT 0.0,
                    vat_amount REAL NOT NULL DEFAULT 0.0,
                    total REAL NOT NULL DEFAULT 0.0,
                    notes TEXT,
                    document_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES documents(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS invoice_items (
                    id TEXT PRIMARY KEY,
                    invoice_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    unit TEXT NOT NULL DEFAULT 'HOURS',
                    unit_price REAL NOT NULL,
                    line_total REAL NOT NULL,
                    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_invoices_period
                ON invoices(period_year, period_month)
            """)

            # Seed defaults
            settings_count = conn.execute("SELECT COUNT(*) FROM finance_settings").fetchone()[0]
            if settings_count == 0:
                now = datetime.now(UTC).isoformat()
                conn.execute(
                    "INSERT INTO finance_settings (tax_rate_default, company_name, company_address, updated_at) VALUES (?, ?, ?, ?)",
                    (0.15, "", "", now),
                )

            cat_count = conn.execute("SELECT COUNT(*) FROM expense_categories").fetchone()[0]
            if cat_count == 0:
                for i, name in enumerate(DEFAULT_CATEGORIES):
                    conn.execute(
                        "INSERT INTO expense_categories (name, is_active, sort_order) VALUES (?, 1, ?)",
                        (name, i),
                    )

            conn.commit()

    # ── Settings ──

    def get_settings(self) -> FinanceSettings:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, tax_rate_default, company_name, company_address, company_tax_id, "
                "company_email, company_phone, company_bank_details, updated_at "
                "FROM finance_settings LIMIT 1"
            ).fetchone()
            return FinanceSettings(*row)

    def update_settings(self, **kwargs) -> FinanceSettings:
        allowed = {
            "tax_rate_default", "company_name", "company_address",
            "company_tax_id", "company_email", "company_phone", "company_bank_details",
        }
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return self.get_settings()
        updates.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE finance_settings SET {', '.join(updates)} WHERE id = 1", params)
            conn.commit()
        return self.get_settings()

    # ── Categories ──

    def list_categories(self, active_only: bool = True) -> list[ExpenseCategory]:
        with sqlite3.connect(self.db_path) as conn:
            sql = "SELECT id, name, is_active, sort_order FROM expense_categories"
            if active_only:
                sql += " WHERE is_active = 1"
            sql += " ORDER BY sort_order ASC, id ASC"
            rows = conn.execute(sql).fetchall()
            return [ExpenseCategory(r[0], r[1], bool(r[2]), r[3]) for r in rows]

    def create_category(self, name: str) -> ExpenseCategory:
        with sqlite3.connect(self.db_path) as conn:
            max_order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) FROM expense_categories").fetchone()[0]
            conn.execute(
                "INSERT INTO expense_categories (name, is_active, sort_order) VALUES (?, 1, ?)",
                (name, max_order + 1),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, name, is_active, sort_order FROM expense_categories WHERE name = ?", (name,)
            ).fetchone()
            return ExpenseCategory(row[0], row[1], bool(row[2]), row[3])

    def rename_category(self, cat_id: int, name: str) -> ExpenseCategory | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE expense_categories SET name = ? WHERE id = ?", (name, cat_id))
            conn.commit()
            row = conn.execute(
                "SELECT id, name, is_active, sort_order FROM expense_categories WHERE id = ?", (cat_id,)
            ).fetchone()
            return ExpenseCategory(row[0], row[1], bool(row[2]), row[3]) if row else None

    def toggle_category(self, cat_id: int, active: bool) -> ExpenseCategory | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE expense_categories SET is_active = ? WHERE id = ?", (int(active), cat_id))
            conn.commit()
            row = conn.execute(
                "SELECT id, name, is_active, sort_order FROM expense_categories WHERE id = ?", (cat_id,)
            ).fetchone()
            return ExpenseCategory(row[0], row[1], bool(row[2]), row[3]) if row else None

    def delete_category(self, cat_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            expense_count = conn.execute(
                "SELECT COUNT(*) FROM expenses WHERE category_id = ?", (cat_id,)
            ).fetchone()[0]
            if expense_count > 0:
                raise ValueError(f"Category has {expense_count} expense(s). Remove them first.")
            deleted = conn.execute("DELETE FROM expense_categories WHERE id = ?", (cat_id,)).rowcount
            conn.commit()
            return deleted > 0

    def reorder_categories(self, ordered_ids: list[int]) -> list[ExpenseCategory]:
        with sqlite3.connect(self.db_path) as conn:
            for position, cat_id in enumerate(ordered_ids):
                conn.execute(
                    "UPDATE expense_categories SET sort_order = ? WHERE id = ?",
                    (position, cat_id),
                )
            conn.commit()
        return self.list_categories(active_only=False)

    # ── Documents ──

    def create_document(
        self,
        original_file_name: str,
        mime_type: str,
        size_bytes: int,
        storage_path: str,
        file_bytes: bytes | None = None,
    ) -> Document:
        doc_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        sha = hashlib.sha256(file_bytes).hexdigest() if file_bytes else None
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO documents (id, original_file_name, mime_type, size_bytes, storage_path, sha256, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (doc_id, original_file_name, mime_type, size_bytes, storage_path, sha, now),
            )
            conn.commit()
        return self.get_document(doc_id)

    def get_document(self, doc_id: str) -> Document | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, original_file_name, mime_type, size_bytes, storage_path, sha256, "
                "ocr_raw_text, ocr_detected_amount, ocr_detected_date_iso, created_at "
                "FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()
            return Document(*row) if row else None

    def delete_document(self, doc_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            # Unlink from expenses
            conn.execute("UPDATE expenses SET document_id = NULL WHERE document_id = ?", (doc_id,))
            deleted = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,)).rowcount
            conn.commit()
            return deleted > 0

    def update_document_ocr(
        self, doc_id: str, raw_text: str | None,
        detected_amount: float | None, detected_date_iso: str | None,
    ) -> Document | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET ocr_raw_text = ?, ocr_detected_amount = ?, ocr_detected_date_iso = ? WHERE id = ?",
                (raw_text, detected_amount, detected_date_iso, doc_id),
            )
            conn.commit()
        return self.get_document(doc_id)

    # ── Expenses ──

    def create_expense(
        self,
        period_year: int,
        period_month: int,
        category_id: int,
        amount: float,
        merchant: str | None = None,
        currency: str = "EUR",
        notes: str | None = None,
        document_id: str | None = None,
        document_not_required: bool = False,
    ) -> Expense:
        expense_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO expenses (id, period_year, period_month, category_id, merchant, amount, "
                "currency, notes, document_id, document_not_required, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (expense_id, period_year, period_month, category_id, merchant, amount,
                 currency, notes, document_id, int(document_not_required), now, now),
            )
            conn.commit()
        return self.get_expense(expense_id)

    def update_expense(self, expense_id: str, **kwargs) -> Expense | None:
        allowed = {
            "period_year", "period_month", "category_id", "merchant",
            "amount", "notes", "document_id", "document_not_required",
        }
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                if k == "document_not_required":
                    v = int(v)
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return self.get_expense(expense_id)
        updates.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(expense_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE expenses SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        return self.get_expense(expense_id)

    def delete_expense(self, expense_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            deleted = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,)).rowcount
            conn.commit()
            return deleted > 0

    def get_expense(self, expense_id: str) -> Expense | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT e.id, e.period_year, e.period_month, e.category_id, "
                "COALESCE(c.name, '(deleted)') as category_name, "
                "e.merchant, e.amount, e.currency, e.notes, e.document_id, "
                "e.document_not_required, e.created_at, e.updated_at "
                "FROM expenses e LEFT JOIN expense_categories c ON e.category_id = c.id "
                "WHERE e.id = ?",
                (expense_id,),
            ).fetchone()
            if not row:
                return None
            return Expense(
                row[0], row[1], row[2], row[3], row[4], row[5],
                row[6], row[7], row[8], row[9], bool(row[10]), row[11], row[12],
            )

    def list_expenses(
        self,
        year: int | None = None,
        month: int | None = None,
        category_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Expense]:
        clauses = []
        params: list = []
        if year is not None:
            clauses.append("e.period_year = ?")
            params.append(year)
        if month is not None:
            clauses.append("e.period_month = ?")
            params.append(month)
        if category_id is not None:
            clauses.append("e.category_id = ?")
            params.append(category_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT e.id, e.period_year, e.period_month, e.category_id, "
            "COALESCE(c.name, '(deleted)') as category_name, "
            "e.merchant, e.amount, e.currency, e.notes, e.document_id, "
            "e.document_not_required, e.created_at, e.updated_at "
            "FROM expenses e LEFT JOIN expense_categories c ON e.category_id = c.id"
            f"{where} ORDER BY e.period_year DESC, e.period_month DESC, e.created_at DESC"
        )
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                Expense(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], bool(r[10]), r[11], r[12])
                for r in rows
            ]

    def count_expenses(
        self,
        year: int | None = None,
        month: int | None = None,
        category_id: int | None = None,
    ) -> int:
        clauses = []
        params: list = []
        if year is not None:
            clauses.append("period_year = ?")
            params.append(year)
        if month is not None:
            clauses.append("period_month = ?")
            params.append(month)
        if category_id is not None:
            clauses.append("category_id = ?")
            params.append(category_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(f"SELECT COUNT(*) FROM expenses{where}", params).fetchone()[0]

    def sum_expenses(self, year: int | None = None, month: int | None = None) -> float:
        clauses = []
        params: list = []
        if year is not None:
            clauses.append("period_year = ?")
            params.append(year)
        if month is not None:
            clauses.append("period_month = ?")
            params.append(month)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(f"SELECT COALESCE(SUM(amount), 0.0) FROM expenses{where}", params).fetchone()
            return row[0]

    # ── Invoices ──

    def create_invoice(
        self,
        period_year: int,
        period_month: int,
        client_name: str,
        invoice_number: str,
        client_address: str | None = None,
        status: str = "PENDING",
        currency: str = "EUR",
        vat_rate: float = 0.0,
        notes: str | None = None,
        document_id: str | None = None,
        items: list[dict] | None = None,
    ) -> Invoice:
        invoice_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        # Calculate totals from items
        subtotal = 0.0
        if items:
            for item in items:
                line_total = _round2(item.get("quantity", 0) * item.get("unit_price", 0))
                subtotal += line_total
        subtotal = _round2(subtotal)
        vat_amount = _round2(subtotal * vat_rate)
        total = _round2(subtotal + vat_amount)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO invoices (id, period_year, period_month, client_name, client_address, "
                "invoice_number, status, currency, vat_rate, subtotal, vat_amount, total, "
                "notes, document_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (invoice_id, period_year, period_month, client_name, client_address,
                 invoice_number, status, currency, vat_rate, subtotal, vat_amount, total,
                 notes, document_id, now, now),
            )
            if items:
                for item in items:
                    line_total = _round2(item.get("quantity", 0) * item.get("unit_price", 0))
                    conn.execute(
                        "INSERT INTO invoice_items (id, invoice_id, description, quantity, unit, unit_price, line_total) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), invoice_id, item["description"],
                         item.get("quantity", 0), item.get("unit", "HOURS"),
                         item.get("unit_price", 0), line_total),
                    )
            conn.commit()
        return self.get_invoice(invoice_id)

    def update_invoice(self, invoice_id: str, **kwargs) -> Invoice | None:
        allowed = {
            "period_year", "period_month", "client_name", "client_address",
            "invoice_number", "status", "vat_rate", "notes", "document_id",
        }
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return self.get_invoice(invoice_id)
        updates.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(invoice_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE invoices SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        # If vat_rate changed, recalculate totals
        if "vat_rate" in kwargs:
            self._recalculate_invoice_totals(invoice_id)
        return self.get_invoice(invoice_id)

    def delete_invoice(self, invoice_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
            deleted = conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,)).rowcount
            conn.commit()
            return deleted > 0

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, period_year, period_month, client_name, client_address, "
                "invoice_number, status, currency, vat_rate, subtotal, vat_amount, total, "
                "notes, document_id, created_at, updated_at FROM invoices WHERE id = ?",
                (invoice_id,),
            ).fetchone()
            return Invoice(*row) if row else None

    def list_invoices(
        self,
        year: int | None = None,
        month: int | None = None,
        client: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Invoice]:
        clauses = []
        params: list = []
        if year is not None:
            clauses.append("period_year = ?")
            params.append(year)
        if month is not None:
            clauses.append("period_month = ?")
            params.append(month)
        if client:
            clauses.append("client_name LIKE ?")
            params.append(f"%{client}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT id, period_year, period_month, client_name, client_address, "
            "invoice_number, status, currency, vat_rate, subtotal, vat_amount, total, "
            "notes, document_id, created_at, updated_at FROM invoices"
            f"{where} ORDER BY period_year DESC, period_month DESC, created_at DESC"
        )
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
            return [Invoice(*r) for r in rows]

    def count_invoices(self, year: int | None = None, month: int | None = None) -> int:
        clauses = []
        params: list = []
        if year is not None:
            clauses.append("period_year = ?")
            params.append(year)
        if month is not None:
            clauses.append("period_month = ?")
            params.append(month)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(f"SELECT COUNT(*) FROM invoices{where}", params).fetchone()[0]

    def sum_invoices(self, year: int | None = None, month: int | None = None) -> float:
        clauses = []
        params: list = []
        if year is not None:
            clauses.append("period_year = ?")
            params.append(year)
        if month is not None:
            clauses.append("period_month = ?")
            params.append(month)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(f"SELECT COALESCE(SUM(total), 0.0) FROM invoices{where}", params).fetchone()[0]

    def sum_pending_invoices(self, year: int | None = None, month: int | None = None) -> float:
        clauses = ["status = 'PENDING'"]
        params: list = []
        if year is not None:
            clauses.append("period_year = ?")
            params.append(year)
        if month is not None:
            clauses.append("period_month = ?")
            params.append(month)
        where = " WHERE " + " AND ".join(clauses)
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(f"SELECT COALESCE(SUM(total), 0.0) FROM invoices{where}", params).fetchone()[0]

    # ── Invoice Items ──

    def get_invoice_items(self, invoice_id: str) -> list[InvoiceItem]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, invoice_id, description, quantity, unit, unit_price, line_total "
                "FROM invoice_items WHERE invoice_id = ? ORDER BY rowid ASC",
                (invoice_id,),
            ).fetchall()
            return [InvoiceItem(*r) for r in rows]

    def set_invoice_items(self, invoice_id: str, items: list[dict]) -> list[InvoiceItem]:
        """Replace all items for an invoice and recalculate totals."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
            for item in items:
                line_total = _round2(item.get("quantity", 0) * item.get("unit_price", 0))
                conn.execute(
                    "INSERT INTO invoice_items (id, invoice_id, description, quantity, unit, unit_price, line_total) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), invoice_id, item["description"],
                     item.get("quantity", 0), item.get("unit", "HOURS"),
                     item.get("unit_price", 0), line_total),
                )
            conn.commit()
        self._recalculate_invoice_totals(invoice_id)
        return self.get_invoice_items(invoice_id)

    def _recalculate_invoice_totals(self, invoice_id: str):
        """Recalculate subtotal, vat_amount, total for an invoice based on its items."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(line_total), 0.0) FROM invoice_items WHERE invoice_id = ?",
                (invoice_id,),
            ).fetchone()
            subtotal = _round2(row[0])
            vat_row = conn.execute(
                "SELECT vat_rate FROM invoices WHERE id = ?", (invoice_id,),
            ).fetchone()
            vat_rate = vat_row[0] if vat_row else 0.0
            vat_amount = _round2(subtotal * vat_rate)
            total = _round2(subtotal + vat_amount)
            now = datetime.now(UTC).isoformat()
            conn.execute(
                "UPDATE invoices SET subtotal = ?, vat_amount = ?, total = ?, updated_at = ? WHERE id = ?",
                (subtotal, vat_amount, total, now, invoice_id),
            )
            conn.commit()
