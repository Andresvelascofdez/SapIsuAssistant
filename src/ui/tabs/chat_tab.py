"""
Assistant Chat tab per PLAN.md section 10 / 11.

Shows chat input, answer output, and source traceability.
"""
import json
import logging
import tkinter as tk
from threading import Thread

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText

from src.shared.app_state import AppState

log = logging.getLogger(__name__)


class ChatTab:
    """Assistant Chat tab."""

    def __init__(self, parent: ttk.Notebook, state: AppState):
        self.state = state
        self.frame = ttk.Frame(parent, padding=10)

        self._build_ui()

    def _build_ui(self):
        # Chat history area
        self.history = ScrolledText(self.frame, autohide=True, height=20)
        self.history.pack(fill=BOTH, expand=True, pady=(0, 8))
        self.history.text.configure(state=tk.DISABLED, wrap=tk.WORD)

        # Sources panel
        sources_frame = ttk.LabelFrame(self.frame, text="Sources (traceability)", padding=5)
        sources_frame.pack(fill=X, pady=(0, 8))

        self.sources_text = tk.Text(sources_frame, height=4, state=tk.DISABLED, wrap=tk.WORD)
        self.sources_text.pack(fill=X)

        # Input area
        input_frame = ttk.Frame(self.frame)
        input_frame.pack(fill=X)

        self.question_var = tk.StringVar()
        self.question_entry = ttk.Entry(
            input_frame,
            textvariable=self.question_var,
        )
        self.question_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.question_entry.bind("<Return>", self._on_send)

        # Reasoning effort
        ttk.Label(input_frame, text="Effort:").pack(side=LEFT, padx=(0, 4))
        self.effort_var = tk.StringVar(value="high")
        effort_combo = ttk.Combobox(
            input_frame,
            textvariable=self.effort_var,
            values=["high", "xhigh"],
            state="readonly",
            width=6,
        )
        effort_combo.pack(side=LEFT, padx=(0, 8))

        self.send_btn = ttk.Button(
            input_frame,
            text="Send",
            command=self._on_send,
            bootstyle="primary",
        )
        self.send_btn.pack(side=LEFT)

    def _on_send(self, _event=None):
        question = self.question_var.get().strip()
        if not question:
            return

        self._append_history(f"You: {question}\n\n")
        self.question_var.set("")
        self.send_btn.configure(state=tk.DISABLED)

        Thread(target=self._do_answer, args=(question,), daemon=True).start()

    def _do_answer(self, question: str):
        try:
            from src.assistant.retrieval.embedding_service import EmbeddingService
            from src.assistant.retrieval.qdrant_service import QdrantService
            from src.assistant.chat.chat_service import ChatService
            from src.assistant.storage.kb_repository import KBItemRepository

            scope = "client" if self.state.active_client_code else "standard"
            code = self.state.active_client_code

            if scope == "client":
                db_path = self.state.data_root / "clients" / code / "assistant_kb.sqlite"
            else:
                db_path = self.state.data_root / "standard" / "assistant_kb.sqlite"

            kb_repo = KBItemRepository(db_path)
            embed_svc = EmbeddingService()
            qdrant_svc = QdrantService(self.state.qdrant_url)
            chat_svc = ChatService(
                embedding_service=embed_svc,
                qdrant_service=qdrant_svc,
            )

            result = chat_svc.answer(
                question=question,
                kb_repo=kb_repo,
                client_scope=scope,
                client_code=code,
                include_standard=self.state.standard_kb_enabled,
                reasoning_effort=self.effort_var.get(),
            )

            self._append_history(f"Assistant: {result.answer}\n\n")
            self._show_sources(result.sources)

        except Exception as e:
            log.exception("Chat error")
            self._append_history(f"Error: {e}\n\n")
        finally:
            self.frame.after(0, lambda: self.send_btn.configure(state=tk.NORMAL))

    def _append_history(self, text: str):
        def _do():
            self.history.text.configure(state=tk.NORMAL)
            self.history.text.insert(tk.END, text)
            self.history.text.configure(state=tk.DISABLED)
            self.history.text.see(tk.END)
        self.frame.after(0, _do)

    def _show_sources(self, sources):
        def _do():
            self.sources_text.configure(state=tk.NORMAL)
            self.sources_text.delete("1.0", tk.END)
            if not sources:
                self.sources_text.insert(tk.END, "No sources used.")
            else:
                for s in sources:
                    tags = json.loads(s.tags_json)
                    self.sources_text.insert(
                        tk.END,
                        f"[{s.type}] {s.title}  (ID: {s.kb_id[:8]}...)  Tags: {', '.join(tags)}\n"
                    )
            self.sources_text.configure(state=tk.DISABLED)
        self.frame.after(0, _do)

    def on_client_changed(self):
        pass
