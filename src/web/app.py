"""
FastAPI application for SAP IS-U Assistant.
"""
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from src.shared.logging_config import configure_logging

_HERE = Path(__file__).resolve().parent

app = FastAPI(title="SAP IS-U Assistant", version="0.1.0")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "sap-assistant-dev-key"))
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
