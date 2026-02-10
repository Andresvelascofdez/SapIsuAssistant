"""
Main application entry point per PLAN.md section 11.

Top bar:
- Active client dropdown
- Standard KB enabled toggle
- Navigation buttons

Tabs:
1. Assistant Chat
2. Knowledge Ingest
3. Knowledge Review
4. Kanban
5. Settings
"""
import tkinter as tk
from pathlib import Path

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from src.shared.app_state import AppState
from src.shared.client_manager import ClientManager
from src.ui.tabs.chat_tab import ChatTab
from src.ui.tabs.ingest_tab import IngestTab
from src.ui.tabs.review_tab import ReviewTab
from src.ui.tabs.kanban_tab import KanbanTab
from src.ui.tabs.settings_tab import SettingsTab


class SapAssistantApp:
    """Main application window."""

    def __init__(self, data_root: Path | None = None):
        self.data_root = data_root or Path("./data")
        self.state = AppState(data_root=self.data_root)
        self.client_manager = ClientManager(self.data_root)

        self.root = ttk.Window(
            title="SAP IS-U Assistant",
            themename="cosmo",
            size=(1200, 800),
            minsize=(900, 600),
        )
        self.root._app_ref = self
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_top_bar()
        self._build_notebook()
        self._refresh_client_list()

    # ------------------------------------------------------------------ top bar
    def _build_top_bar(self):
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill=X)

        # Client selector
        ttk.Label(bar, text="Client:").pack(side=LEFT, padx=(0, 4))

        self.client_var = tk.StringVar(value="(none)")
        self.client_combo = ttk.Combobox(
            bar,
            textvariable=self.client_var,
            state="readonly",
            width=18,
        )
        self.client_combo.pack(side=LEFT, padx=(0, 12))
        self.client_combo.bind("<<ComboboxSelected>>", self._on_client_changed)

        # Standard KB toggle
        self.std_kb_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bar,
            text="Standard KB",
            variable=self.std_kb_var,
            bootstyle="round-toggle",
            command=self._on_std_kb_toggled,
        ).pack(side=LEFT, padx=(0, 20))

        # Status label (right side)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.status_var).pack(side=RIGHT)

    # --------------------------------------------------------------- notebook
    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root, bootstyle="default")
        self.notebook.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        self.chat_tab = ChatTab(self.notebook, self.state)
        self.ingest_tab = IngestTab(self.notebook, self.state, self.client_manager)
        self.review_tab = ReviewTab(self.notebook, self.state, self.client_manager)
        self.kanban_tab = KanbanTab(self.notebook, self.state, self.client_manager)
        self.settings_tab = SettingsTab(self.notebook, self.state, self.client_manager)

        self.notebook.add(self.chat_tab.frame, text="Assistant Chat")
        self.notebook.add(self.ingest_tab.frame, text="Knowledge Ingest")
        self.notebook.add(self.review_tab.frame, text="Knowledge Review")
        self.notebook.add(self.kanban_tab.frame, text="Kanban")
        self.notebook.add(self.settings_tab.frame, text="Settings")

    # --------------------------------------------------------------- callbacks
    def _refresh_client_list(self):
        clients = self.client_manager.list_clients()
        codes = [c.code for c in clients]
        self.client_combo["values"] = ["(none)"] + codes

        if self.state.active_client_code in codes:
            self.client_var.set(self.state.active_client_code)
        else:
            self.client_var.set("(none)")
            self.state.active_client_code = None

    def _on_client_changed(self, _event=None):
        val = self.client_var.get()
        if val == "(none)":
            self.state.active_client_code = None
        else:
            self.state.active_client_code = val
        self.status_var.set(f"Active client: {val}")
        self._notify_tabs()

    def _on_std_kb_toggled(self):
        self.state.standard_kb_enabled = self.std_kb_var.get()

    def _on_close(self):
        self.root.destroy()

    def _notify_tabs(self):
        """Notify tabs that client changed so they can refresh."""
        for tab in (self.chat_tab, self.ingest_tab, self.review_tab, self.kanban_tab, self.settings_tab):
            if hasattr(tab, "on_client_changed"):
                tab.on_client_changed()

    def refresh_clients(self):
        """Public method for settings tab to refresh client list."""
        self._refresh_client_list()

    def run(self):
        self.root.mainloop()


def main():
    app = SapAssistantApp()
    app.run()


if __name__ == "__main__":
    main()
