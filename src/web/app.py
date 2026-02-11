"""
FastAPI application for SAP IS-U Assistant.
"""
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from src.shared.logging_config import configure_logging

_HERE = Path(__file__).resolve().parent
_DATA_ROOT = Path(os.environ.get("SAP_DATA_ROOT", "./data"))

log = logging.getLogger(__name__)


def _get_session_secret() -> str:
    """Get or generate a persistent session secret key."""
    env_key = os.environ.get("SESSION_SECRET")
    if env_key:
        return env_key
    _DATA_ROOT.mkdir(parents=True, exist_ok=True)
    key_file = _DATA_ROOT / ".session_key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_hex(32)
    key_file.write_text(key)
    return key


def _run_retention_cleanup():
    """Run chat history retention cleanup on startup."""
    try:
        from src.assistant.storage.chat_repository import ChatRepository
        db_path = _DATA_ROOT / "chat_history.sqlite"
        if db_path.exists():
            chat_repo = ChatRepository(db_path)
            default_days = int(os.environ.get("CHAT_RETENTION_DAYS", "30"))
            deleted = chat_repo.cleanup_retention(default_days)
            if deleted:
                log.info("Retention cleanup: deleted %d old chat sessions", deleted)
    except Exception as e:
        log.warning("Retention cleanup failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    _run_retention_cleanup()
    yield


app = FastAPI(title="SAP IS-U Assistant", version="0.2.2", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=_get_session_secret())
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")

# Import and include routers
from src.web.routers import settings, kanban, review, ingest, chat  # noqa: E402

app.include_router(chat.router)
app.include_router(ingest.router)
app.include_router(review.router)
app.include_router(kanban.router)
app.include_router(settings.router)


@app.get("/")
async def index():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/chat")


def main():
    configure_logging()
    uvicorn.run(
        "src.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
