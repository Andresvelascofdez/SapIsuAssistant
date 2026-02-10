"""
Kanban tab per PLAN.md section 11.

Board with columns for ticket status, CRUD, and history.
"""
import json
import logging
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from src.shared.app_state import AppState
from src.shared.client_manager import ClientManager

log = logging.getLogger(__name__)

COLUMNS = ["OPEN", "IN_PROGRESS", "WAITING", "DONE"]


class KanbanTab:
    """Kanban tab with column-based board."""

    def __init__(self, parent: ttk.Notebook, state: AppState, client_manager: ClientManager):
        self.state = state
        self.client_manager = client_manager
        self.frame = ttk.Frame(parent, padding=10)
        self._tickets_by_col = {}

        self._build_ui()

    def _build_ui(self):
        # Top bar
        top = ttk.Frame(self.frame)
        top.pack(fill=X, pady=(0, 8))

        ttk.Button(top, text="New Ticket", command=self._on_new_ticket, bootstyle="success").pack(side=LEFT, padx=(0, 8))
        ttk.Button(top, text="Refresh", command=self._on_refresh, bootstyle="info").pack(side=LEFT, padx=(0, 8))

        self.kanban_status_var = tk.StringVar()
        ttk.Label(top, textvariable=self.kanban_status_var).pack(side=RIGHT)

        # Board columns
        board = ttk.Frame(self.frame)
        board.pack(fill=BOTH, expand=True)

        self.col_listboxes = {}
        for i, col_name in enumerate(COLUMNS):
            col_frame = ttk.LabelFrame(board, text=col_name, padding=4)
            col_frame.grid(row=0, column=i, sticky=NSEW, padx=4)
            board.columnconfigure(i, weight=1)
            board.rowconfigure(0, weight=1)

            lb = tk.Listbox(col_frame, exportselection=False)
            lb.pack(fill=BOTH, expand=True)
            lb.bind("<Double-Button-1>", lambda e, c=col_name: self._on_ticket_double_click(c))
            self.col_listboxes[col_name] = lb

        # Detail / move panel
        detail = ttk.LabelFrame(self.frame, text="Ticket Detail", padding=8)
        detail.pack(fill=X, pady=(8, 0))

        row1 = ttk.Frame(detail)
        row1.pack(fill=X, pady=(0, 4))

        ttk.Label(row1, text="Title:").pack(side=LEFT, padx=(0, 4))
        self.detail_title_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.detail_title_var, width=40).pack(side=LEFT, padx=(0, 12))

        ttk.Label(row1, text="Priority:").pack(side=LEFT, padx=(0, 4))
        self.detail_priority_var = tk.StringVar(value="MEDIUM")
        ttk.Combobox(
            row1,
            textvariable=self.detail_priority_var,
            values=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
            state="readonly",
            width=10,
        ).pack(side=LEFT, padx=(0, 12))

        ttk.Label(row1, text="Move to:").pack(side=LEFT, padx=(0, 4))
        self.move_var = tk.StringVar()
        ttk.Combobox(
            row1,
            textvariable=self.move_var,
            values=COLUMNS + ["CLOSED"],
            state="readonly",
            width=14,
        ).pack(side=LEFT, padx=(0, 8))

        ttk.Button(row1, text="Move", command=self._on_move, bootstyle="warning").pack(side=LEFT)

        row2 = ttk.Frame(detail)
        row2.pack(fill=X, pady=(0, 4))

        ttk.Label(row2, text="Notes:").pack(side=LEFT, padx=(0, 4))
        self.detail_notes_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.detail_notes_var, width=60).pack(side=LEFT, fill=X, expand=True, padx=(0, 8))

        ttk.Button(row2, text="Save", command=self._on_save_detail, bootstyle="primary").pack(side=LEFT)

        self._selected_ticket_id = None

    def _get_repo(self):
        from src.kanban.storage.kanban_repository import KanbanRepository

        code = self.state.active_client_code
        if not code:
            return None

        db_path = self.state.data_root / "clients" / code / "kanban.sqlite"
        if not db_path.parent.exists():
            return None

        return KanbanRepository(db_path)

    def _on_refresh(self):
        repo = self._get_repo()
        if not repo:
            self.kanban_status_var.set("Select a client first")
            for lb in self.col_listboxes.values():
                lb.delete(0, tk.END)
            return

        all_tickets = repo.list_tickets()
        self._tickets_by_col = {col: [] for col in COLUMNS}

        for t in all_tickets:
            if t.status in self._tickets_by_col:
                self._tickets_by_col[t.status].append(t)

        for col_name, lb in self.col_listboxes.items():
            lb.delete(0, tk.END)
            for t in self._tickets_by_col.get(col_name, []):
                label = f"[{t.priority}] {t.title}"
                lb.insert(tk.END, label)

        total = len(all_tickets)
        self.kanban_status_var.set(f"{total} tickets")

    def _on_ticket_double_click(self, column: str):
        lb = self.col_listboxes[column]
        sel = lb.curselection()
        if not sel:
            return

        ticket = self._tickets_by_col[column][sel[0]]
        self._selected_ticket_id = ticket.id
        self.detail_title_var.set(ticket.title)
        self.detail_priority_var.set(ticket.priority)
        self.detail_notes_var.set(ticket.notes or "")
        self.move_var.set(ticket.status)

    def _on_new_ticket(self):
        repo = self._get_repo()
        if not repo:
            self.kanban_status_var.set("Select a client first")
            return

        title = self.detail_title_var.get().strip()
        if not title:
            self.kanban_status_var.set("Enter a title first")
            return

        repo.create_ticket(
            title=title,
            priority=self.detail_priority_var.get(),
            notes=self.detail_notes_var.get().strip() or None,
        )
        self._on_refresh()
        self.kanban_status_var.set(f"Created: {title}")

    def _on_move(self):
        if not self._selected_ticket_id:
            return

        repo = self._get_repo()
        if not repo:
            return

        new_status = self.move_var.get()
        repo.update_status(self._selected_ticket_id, new_status)
        self._on_refresh()

    def _on_save_detail(self):
        if not self._selected_ticket_id:
            return

        repo = self._get_repo()
        if not repo:
            return

        repo.update_ticket(
            self._selected_ticket_id,
            title=self.detail_title_var.get().strip() or None,
            priority=self.detail_priority_var.get(),
            notes=self.detail_notes_var.get().strip() or None,
        )
        self._on_refresh()
        self.kanban_status_var.set("Ticket updated")

    def on_client_changed(self):
        self._selected_ticket_id = None
        self._on_refresh()
