"""
Settings tab per PLAN.md section 11.

Register clients, configure Qdrant URL, manage OpenAI key.
"""
import logging
import os
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from src.shared.app_state import AppState
from src.shared.client_manager import ClientManager

log = logging.getLogger(__name__)


class SettingsTab:
    """Settings tab for client management and configuration."""

    def __init__(self, parent: ttk.Notebook, state: AppState, client_manager: ClientManager):
        self.state = state
        self.client_manager = client_manager
        self.frame = ttk.Frame(parent, padding=10)

        self._build_ui()
        self._refresh_clients()

    def _build_ui(self):
        # --- Client Management ---
        client_section = ttk.LabelFrame(self.frame, text="Client Management", padding=10)
        client_section.pack(fill=X, pady=(0, 12))

        reg_frame = ttk.Frame(client_section)
        reg_frame.pack(fill=X, pady=(0, 8))

        ttk.Label(reg_frame, text="Code:").pack(side=LEFT, padx=(0, 4))
        self.new_code_var = tk.StringVar()
        ttk.Entry(reg_frame, textvariable=self.new_code_var, width=12).pack(side=LEFT, padx=(0, 8))

        ttk.Label(reg_frame, text="Name:").pack(side=LEFT, padx=(0, 4))
        self.new_name_var = tk.StringVar()
        ttk.Entry(reg_frame, textvariable=self.new_name_var, width=30).pack(side=LEFT, padx=(0, 8))

        ttk.Button(reg_frame, text="Register Client", command=self._on_register, bootstyle="success").pack(side=LEFT)

        # Client list
        self.client_listbox = tk.Listbox(client_section, height=6, exportselection=False)
        self.client_listbox.pack(fill=X)

        self.client_status_var = tk.StringVar()
        ttk.Label(client_section, textvariable=self.client_status_var).pack(anchor=W, pady=(4, 0))

        # --- Qdrant Configuration ---
        qdrant_section = ttk.LabelFrame(self.frame, text="Qdrant Configuration", padding=10)
        qdrant_section.pack(fill=X, pady=(0, 12))

        qdrant_row = ttk.Frame(qdrant_section)
        qdrant_row.pack(fill=X)

        ttk.Label(qdrant_row, text="URL:").pack(side=LEFT, padx=(0, 4))
        self.qdrant_url_var = tk.StringVar(value=self.state.qdrant_url)
        ttk.Entry(qdrant_row, textvariable=self.qdrant_url_var, width=40).pack(side=LEFT, padx=(0, 8))
        ttk.Button(qdrant_row, text="Apply", command=self._on_apply_qdrant).pack(side=LEFT)

        # --- OpenAI Configuration ---
        openai_section = ttk.LabelFrame(self.frame, text="OpenAI Configuration", padding=10)
        openai_section.pack(fill=X, pady=(0, 12))

        key_row = ttk.Frame(openai_section)
        key_row.pack(fill=X)

        ttk.Label(key_row, text="API Key:").pack(side=LEFT, padx=(0, 4))
        self.api_key_var = tk.StringVar(value=os.environ.get("OPENAI_API_KEY", ""))
        ttk.Entry(key_row, textvariable=self.api_key_var, width=50, show="*").pack(side=LEFT, padx=(0, 8))
        ttk.Button(key_row, text="Set", command=self._on_set_api_key).pack(side=LEFT)

        has_key = "Set" if os.environ.get("OPENAI_API_KEY") else "Not set"
        self.key_status_var = tk.StringVar(value=f"Status: {has_key}")
        ttk.Label(openai_section, textvariable=self.key_status_var).pack(anchor=W, pady=(4, 0))

        # --- Data Info ---
        info_section = ttk.LabelFrame(self.frame, text="Data Info", padding=10)
        info_section.pack(fill=X)

        self.info_var = tk.StringVar(value=f"Data root: {self.state.data_root.resolve()}")
        ttk.Label(info_section, textvariable=self.info_var).pack(anchor=W)

    def _refresh_clients(self):
        self.client_listbox.delete(0, tk.END)
        clients = self.client_manager.list_clients()
        for c in clients:
            self.client_listbox.insert(tk.END, f"{c.code} - {c.name}")
        self.client_status_var.set(f"{len(clients)} clients registered")

    def _on_register(self):
        code = self.new_code_var.get().strip()
        name = self.new_name_var.get().strip()

        if not code or not name:
            self.client_status_var.set("Error: code and name required")
            return

        try:
            self.client_manager.register_client(code, name)
            self.client_status_var.set(f"Registered: {code}")
            self.new_code_var.set("")
            self.new_name_var.set("")
            self._refresh_clients()

            # Notify parent app to refresh client dropdown
            app = self.frame.winfo_toplevel()
            if hasattr(app, "_app_ref"):
                app._app_ref.refresh_clients()
        except ValueError as e:
            self.client_status_var.set(f"Error: {e}")

    def _on_apply_qdrant(self):
        url = self.qdrant_url_var.get().strip()
        if url:
            self.state.qdrant_url = url

    def _on_set_api_key(self):
        key = self.api_key_var.get().strip()
        if key:
            os.environ["OPENAI_API_KEY"] = key
            self.key_status_var.set("Status: Set (session only)")
        else:
            self.key_status_var.set("Status: Not set")

    def on_client_changed(self):
        pass
