"""
Dependency injection for FastAPI routes.
"""
import os
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.shared.app_state import AppState
from src.shared.client_manager import ClientManager

_HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=_HERE / "templates")

DATA_ROOT = Path(os.environ.get("SAP_DATA_ROOT", "./data"))


def get_state(request: Request) -> AppState:
    """Reconstruct AppState from session."""
    session = request.session
    return AppState(
        data_root=DATA_ROOT,
        active_client_code=session.get("active_client_code"),
        standard_kb_enabled=session.get("standard_kb_enabled", True),
        qdrant_url=session.get("qdrant_url", "http://localhost:6333"),
        chat_retention_days=session.get("chat_retention_days", 30),
        stale_ticket_days=session.get("stale_ticket_days", 3),
    )


def get_openai_api_key(request: Request) -> str | None:
    """Get OpenAI API key from session or env."""
    key = request.session.get("openai_api_key")
    if key:
        return key
    return os.environ.get("OPENAI_API_KEY")


def get_client_manager() -> ClientManager:
    """Get ClientManager instance."""
    return ClientManager(DATA_ROOT)


def get_chat_repository():
    """Get ChatRepository instance for global chat history."""
    from src.assistant.storage.chat_repository import ChatRepository
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    return ChatRepository(DATA_ROOT / "chat_history.sqlite")


def get_template_context(request: Request) -> dict:
    """Build common template context with nav state."""
    state = get_state(request)
    cm = get_client_manager()
    clients = cm.list_clients()
    return {
        "request": request,
        "active_client": state.active_client_code,
        "standard_kb_enabled": state.standard_kb_enabled,
        "qdrant_url": state.qdrant_url,
        "clients": [c.code for c in clients],
        "chat_retention_days": state.chat_retention_days,
        "stale_ticket_days": state.stale_ticket_days,
    }


def get_finance_repository():
    """Get FinanceRepository instance for global finance data."""
    from src.finance.storage.finance_repository import FinanceRepository
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    return FinanceRepository(DATA_ROOT / "finance.sqlite")
