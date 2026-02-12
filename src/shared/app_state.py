"""
Application state: shared mutable state for the running app.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AppState:
    """Global application state used by all UI tabs."""
    data_root: Path
    active_client_code: Optional[str] = None
    standard_kb_enabled: bool = True
    qdrant_url: str = "http://localhost:6333"
    chat_retention_days: int = 30
    stale_ticket_days: int = 3
