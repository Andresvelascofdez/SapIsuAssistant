"""
Knowledge Review tab per PLAN.md section 8.4 / 11.

Shows synthesized KB items for review/edit/approve/reject.
Approve triggers embedding + Qdrant upsert.
"""
import json
import logging
import tkinter as tk
from threading import Thread

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.tableview import Tableview

from src.shared.app_state import AppState
from src.shared.client_manager import ClientManager

log = logging.getLogger(__name__)


class ReviewTab:
    """Knowledge Review tab."""

    def __init__(self, parent: ttk.Notebook, state: AppState, client_manager: ClientManager):
        self.state = state
        self.client_manager = client_manager
        self.frame = ttk.Frame(parent, padding=10)

        self._current_items = []
        self._selected_index = None

        self._build_ui()

    def _build_ui(self):
        # Top controls
        top = ttk.Frame(self.frame)
        top.pack(fill=X, pady=(0, 8))

        ttk.Label(top, text="Scope:").pack(side=LEFT, padx=(0, 4))
        self.scope_var = tk.StringVar(value="standard")
        ttk.Radiobutton(top, text="Standard", variable=self.scope_var, value="standard").pack(side=LEFT, padx=(0, 8))
        ttk.Radiobutton(top, text="Active Client", variable=self.scope_var, value="client").pack(side=LEFT, padx=(0, 12))

        ttk.Label(top, text="Filter:").pack(side=LEFT, padx=(0, 4))
        self.filter_var = tk.StringVar(value="DRAFT")
        filter_combo = ttk.Combobox(
            top,
            textvariable=self.filter_var,
            values=["DRAFT", "APPROVED", "REJECTED", "ALL"],
            state="readonly",
            width=12,
        )
        filter_combo.pack(side=LEFT, padx=(0, 8))

        ttk.Button(top, text="Refresh", command=self._on_refresh, bootstyle="info").pack(side=LEFT)

        # Paned layout: list left, detail right
        paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        paned.pack(fill=BOTH, expand=True, pady=(0, 8))

        # Item list (left)
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)

        self.item_listbox = tk.Listbox(list_frame, exportselection=False)
        self.item_listbox.pack(fill=BOTH, expand=True)
        self.item_listbox.bind("<<ListboxSelect>>", self._on_item_selected)

        # Detail panel (right)
        detail_frame = ttk.Frame(paned, padding=8)
        paned.add(detail_frame, weight=2)

        # Fields
        fields_frame = ttk.Frame(detail_frame)
        fields_frame.pack(fill=X, pady=(0, 4))

        ttk.Label(fields_frame, text="Type:").grid(row=0, column=0, sticky=W, padx=(0, 4))
        self.type_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self.type_var, state="readonly", width=25).grid(row=0, column=1, sticky=W)

        ttk.Label(fields_frame, text="Title:").grid(row=1, column=0, sticky=W, padx=(0, 4), pady=4)
        self.title_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self.title_var, width=50).grid(row=1, column=1, sticky=EW, pady=4)

        ttk.Label(fields_frame, text="Tags:").grid(row=2, column=0, sticky=W, padx=(0, 4))
        self.tags_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self.tags_var, width=50).grid(row=2, column=1, sticky=EW)

        ttk.Label(fields_frame, text="SAP Objects:").grid(row=3, column=0, sticky=W, padx=(0, 4), pady=4)
        self.sap_obj_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self.sap_obj_var, width=50).grid(row=3, column=1, sticky=EW, pady=4)

        ttk.Label(fields_frame, text="Status:").grid(row=4, column=0, sticky=W, padx=(0, 4))
        self.status_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self.status_var, state="readonly", width=15).grid(row=4, column=1, sticky=W)

        fields_frame.columnconfigure(1, weight=1)

        # Content markdown
        ttk.Label(detail_frame, text="Content (Markdown):").pack(anchor=W, pady=(8, 2))
        self.content_text = ScrolledText(detail_frame, autohide=True, height=12)
        self.content_text.pack(fill=BOTH, expand=True, pady=(0, 8))

        # Action buttons
        btn_frame = ttk.Frame(detail_frame)
        btn_frame.pack(fill=X)

        self.approve_btn = ttk.Button(btn_frame, text="Approve", command=self._on_approve, bootstyle="success")
        self.approve_btn.pack(side=LEFT, padx=(0, 8))

        self.reject_btn = ttk.Button(btn_frame, text="Reject", command=self._on_reject, bootstyle="danger")
        self.reject_btn.pack(side=LEFT, padx=(0, 8))

        self.review_status_var = tk.StringVar()
        ttk.Label(btn_frame, textvariable=self.review_status_var).pack(side=LEFT)

    def _get_db_path(self, scope: str) -> "Path":
        from pathlib import Path as P
        if scope == "client" and self.state.active_client_code:
            return self.state.data_root / "clients" / self.state.active_client_code / "assistant_kb.sqlite"
        return self.state.data_root / "standard" / "assistant_kb.sqlite"

    def _on_refresh(self):
        from src.assistant.storage.kb_repository import KBItemRepository
        from src.assistant.storage.models import KBItemStatus

        scope = self.scope_var.get()
        client_code = self.state.active_client_code if scope == "client" else None

        if scope == "client" and not client_code:
            self.review_status_var.set("Select a client first")
            return

        db_path = self._get_db_path(scope)
        if not db_path.exists():
            self._current_items = []
            self.item_listbox.delete(0, tk.END)
            self.review_status_var.set("No KB database found")
            return

        repo = KBItemRepository(db_path)
        filter_val = self.filter_var.get()

        if filter_val == "ALL":
            items = repo.list_by_scope(scope, client_code)
        else:
            items = repo.list_by_scope(scope, client_code, KBItemStatus(filter_val))

        self._current_items = items
        self.item_listbox.delete(0, tk.END)

        for item in items:
            self.item_listbox.insert(tk.END, f"[{item.type}] {item.title} (v{item.version})")

        self.review_status_var.set(f"{len(items)} items found")

    def _on_item_selected(self, _event=None):
        sel = self.item_listbox.curselection()
        if not sel:
            return

        idx = sel[0]
        self._selected_index = idx
        item = self._current_items[idx]

        self.type_var.set(item.type)
        self.title_var.set(item.title)
        self.tags_var.set(", ".join(json.loads(item.tags_json)))
        self.sap_obj_var.set(", ".join(json.loads(item.sap_objects_json)))
        self.status_var.set(item.status)

        self.content_text.text.configure(state=tk.NORMAL)
        self.content_text.text.delete("1.0", tk.END)
        self.content_text.text.insert("1.0", item.content_markdown)

    def _on_approve(self):
        if self._selected_index is None:
            return
        Thread(target=self._do_approve, daemon=True).start()

    def _do_approve(self):
        from src.assistant.storage.kb_repository import KBItemRepository
        from src.assistant.storage.models import KBItemStatus

        item = self._current_items[self._selected_index]
        scope = self.scope_var.get()
        db_path = self._get_db_path(scope)
        repo = KBItemRepository(db_path)

        # Update status to APPROVED
        repo.update_status(item.kb_id, KBItemStatus.APPROVED)
        updated = repo.get_by_id(item.kb_id)

        # Embed and upsert to Qdrant
        try:
            from src.assistant.retrieval.embedding_service import EmbeddingService
            from src.assistant.retrieval.qdrant_service import QdrantService

            embed_svc = EmbeddingService()
            embedding = embed_svc.embed(f"{updated.title}\n\n{updated.content_markdown}")

            qdrant_svc = QdrantService(self.state.qdrant_url)
            qdrant_svc.upsert_kb_item(updated, embedding)

            self._set_review_status(f"Approved and indexed: {updated.title}")
        except Exception as e:
            log.exception("Qdrant upsert error")
            self._set_review_status(f"Approved (Qdrant error: {e})")

        self.frame.after(0, self._on_refresh)

    def _on_reject(self):
        if self._selected_index is None:
            return

        from src.assistant.storage.kb_repository import KBItemRepository
        from src.assistant.storage.models import KBItemStatus

        item = self._current_items[self._selected_index]
        scope = self.scope_var.get()
        db_path = self._get_db_path(scope)
        repo = KBItemRepository(db_path)

        repo.update_status(item.kb_id, KBItemStatus.REJECTED)
        self.review_status_var.set(f"Rejected: {item.title}")
        self._on_refresh()

    def _set_review_status(self, msg: str):
        self.frame.after(0, lambda: self.review_status_var.set(msg))

    def on_client_changed(self):
        self._on_refresh()
