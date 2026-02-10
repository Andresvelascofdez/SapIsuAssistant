"""
Knowledge Ingest tab per PLAN.md section 8 / 11.

Supports free text, PDF, DOCX ingestion.
Triggers synthesis and stores drafts for review.
"""
import hashlib
import logging
import shutil
import tkinter as tk
from pathlib import Path
from threading import Thread
from tkinter import filedialog

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText

from src.shared.app_state import AppState
from src.shared.client_manager import ClientManager

log = logging.getLogger(__name__)


class IngestTab:
    """Knowledge Ingest tab."""

    def __init__(self, parent: ttk.Notebook, state: AppState, client_manager: ClientManager):
        self.state = state
        self.client_manager = client_manager
        self.frame = ttk.Frame(parent, padding=10)

        self._build_ui()

    def _build_ui(self):
        # Scope selector
        scope_frame = ttk.Frame(self.frame)
        scope_frame.pack(fill=X, pady=(0, 8))

        ttk.Label(scope_frame, text="Target scope:").pack(side=LEFT, padx=(0, 8))
        self.scope_var = tk.StringVar(value="standard")
        ttk.Radiobutton(scope_frame, text="Standard", variable=self.scope_var, value="standard").pack(side=LEFT, padx=(0, 8))
        ttk.Radiobutton(scope_frame, text="Active Client", variable=self.scope_var, value="client").pack(side=LEFT)

        # Input type selector
        type_frame = ttk.Frame(self.frame)
        type_frame.pack(fill=X, pady=(0, 8))

        ttk.Label(type_frame, text="Input type:").pack(side=LEFT, padx=(0, 8))
        self.input_type_var = tk.StringVar(value="text")
        ttk.Radiobutton(type_frame, text="Free text", variable=self.input_type_var, value="text", command=self._on_type_changed).pack(side=LEFT, padx=(0, 8))
        ttk.Radiobutton(type_frame, text="PDF", variable=self.input_type_var, value="pdf", command=self._on_type_changed).pack(side=LEFT, padx=(0, 8))
        ttk.Radiobutton(type_frame, text="DOCX", variable=self.input_type_var, value="docx", command=self._on_type_changed).pack(side=LEFT)

        # File picker (hidden for text)
        self.file_frame = ttk.Frame(self.frame)
        self.file_frame.pack(fill=X, pady=(0, 8))

        self.file_path_var = tk.StringVar()
        ttk.Entry(self.file_frame, textvariable=self.file_path_var, state="readonly").pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.browse_btn = ttk.Button(self.file_frame, text="Browse...", command=self._on_browse)
        self.browse_btn.pack(side=LEFT)
        self.file_frame.pack_forget()  # Hidden initially

        # Text input area
        ttk.Label(self.frame, text="Paste content:").pack(anchor=W)
        self.text_input = ScrolledText(self.frame, autohide=True, height=15)
        self.text_input.pack(fill=BOTH, expand=True, pady=(0, 8))

        # Status + button
        bottom = ttk.Frame(self.frame)
        bottom.pack(fill=X)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bottom, textvariable=self.status_var).pack(side=LEFT)

        self.ingest_btn = ttk.Button(
            bottom,
            text="Ingest and Synthesize",
            command=self._on_ingest,
            bootstyle="success",
        )
        self.ingest_btn.pack(side=RIGHT)

    def _on_type_changed(self):
        if self.input_type_var.get() == "text":
            self.file_frame.pack_forget()
            self.text_input.pack(fill=BOTH, expand=True, pady=(0, 8))
        else:
            self.text_input.pack_forget()
            self.file_frame.pack(fill=X, pady=(0, 8), before=self.frame.winfo_children()[-1])

    def _on_browse(self):
        input_type = self.input_type_var.get()
        if input_type == "pdf":
            filetypes = [("PDF files", "*.pdf")]
        else:
            filetypes = [("Word documents", "*.docx")]

        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            self.file_path_var.set(path)

    def _on_ingest(self):
        self.ingest_btn.configure(state=tk.DISABLED)
        self.status_var.set("Processing...")
        Thread(target=self._do_ingest, daemon=True).start()

    def _do_ingest(self):
        try:
            from src.assistant.ingestion.extractors import extract_text, extract_pdf, extract_docx
            from src.assistant.ingestion.synthesis import SynthesisPipeline, SynthesisError
            from src.assistant.storage.ingestion_repository import IngestionRepository
            from src.assistant.storage.kb_repository import KBItemRepository
            from src.assistant.storage.models import IngestionStatus, KBItemStatus, KBItemType
            import json

            scope = self.scope_var.get()
            client_code = self.state.active_client_code if scope == "client" else None

            if scope == "client" and not client_code:
                self._set_status("Error: Select a client first")
                return

            # 1. Extract
            input_type = self.input_type_var.get()
            if input_type == "text":
                raw = self.text_input.text.get("1.0", tk.END).strip()
                if not raw:
                    self._set_status("Error: No text provided")
                    return
                extraction = extract_text(raw)
            elif input_type == "pdf":
                path = self.file_path_var.get()
                if not path:
                    self._set_status("Error: No file selected")
                    return
                extraction = extract_pdf(Path(path))
                self._copy_upload(Path(path), scope, client_code, extraction.input_hash)
            else:
                path = self.file_path_var.get()
                if not path:
                    self._set_status("Error: No file selected")
                    return
                extraction = extract_docx(Path(path))
                self._copy_upload(Path(path), scope, client_code, extraction.input_hash)

            self._set_status("Extracted. Calling OpenAI for synthesis...")

            # 2. Get DB path
            if scope == "client":
                db_path = self.state.data_root / "clients" / client_code / "assistant_kb.sqlite"
            else:
                db_path = self.state.data_root / "standard" / "assistant_kb.sqlite"
                db_path.parent.mkdir(parents=True, exist_ok=True)

            ingestion_repo = IngestionRepository(db_path)
            kb_repo = KBItemRepository(db_path)

            # 3. Create ingestion record
            ingestion = ingestion_repo.create(
                client_scope=scope,
                client_code=client_code,
                input_kind=extraction.input_kind,
                input_hash=extraction.input_hash,
                input_name=extraction.input_name,
                model_used="gpt-5.2",
                reasoning_effort="xhigh",
                status=IngestionStatus.DRAFT,
            )

            # 4. Synthesize
            try:
                pipeline = SynthesisPipeline()
                result = pipeline.synthesize(extraction.text)
                ingestion_repo.update_status(ingestion.ingestion_id, IngestionStatus.SYNTHESIZED)
            except SynthesisError as e:
                ingestion_repo.update_status(ingestion.ingestion_id, IngestionStatus.FAILED)
                self._set_status(f"Synthesis failed: {e}")
                return

            # 5. Store KB items as DRAFT
            count = 0
            for raw_item in result["kb_items"]:
                kb_repo.create_or_update(
                    client_scope=scope,
                    client_code=client_code,
                    item_type=KBItemType(raw_item["type"]),
                    title=raw_item["title"],
                    content_markdown=raw_item["content_markdown"],
                    tags=raw_item["tags"],
                    sap_objects=raw_item["sap_objects"],
                    signals=raw_item["signals"],
                    sources={"ingestion_id": ingestion.ingestion_id, "input_hash": extraction.input_hash},
                    status=KBItemStatus.DRAFT,
                )
                count += 1

            self._set_status(f"Done: {count} KB items created as DRAFT. Go to Review tab to approve.")

            # Clear input
            self.frame.after(0, lambda: self.text_input.text.delete("1.0", tk.END))
            self.frame.after(0, lambda: self.file_path_var.set(""))

        except Exception as e:
            log.exception("Ingestion error")
            self._set_status(f"Error: {e}")
        finally:
            self.frame.after(0, lambda: self.ingest_btn.configure(state=tk.NORMAL))

    def _copy_upload(self, src_path: Path, scope: str, client_code: str | None, input_hash: str):
        """Copy uploaded file to uploads/ with hash-based name per PLAN.md section 8.2."""
        if scope == "client":
            uploads_dir = self.state.data_root / "clients" / client_code / "uploads"
        else:
            uploads_dir = self.state.data_root / "standard" / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        ext = src_path.suffix
        dest = uploads_dir / f"{input_hash}{ext}"
        if not dest.exists():
            shutil.copy2(src_path, dest)

    def _set_status(self, msg: str):
        self.frame.after(0, lambda: self.status_var.set(msg))

    def on_client_changed(self):
        pass
