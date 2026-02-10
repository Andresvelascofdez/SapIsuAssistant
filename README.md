# SAP IS-U Assistant + Kanban

A web application providing AI-powered knowledge management and operational tracking for SAP IS-U systems.

## Features

- **Assistant Module**: AI-powered knowledge base with RAG (Retrieval Augmented Generation)
  - Ingest knowledge from text, PDF, DOCX
  - Structured synthesis using OpenAI GPT-5.2
  - Client-isolated knowledge bases
  - Vector search via Qdrant
  - SSE-based streaming chat responses

- **Kanban Module**: Operational ticket tracking
  - Drag-and-drop board (SortableJS)
  - Status, priority, notes, tags
  - Ticket history tracking
  - Independent from assistant knowledge base
  - Client-isolated boards

- **Review Module**: KB item approval workflow
  - Edit title, content, tags, SAP objects before approval
  - Approve + auto-index in Qdrant
  - Reject with status tracking

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn (Web backend)
- Jinja2 + Tailwind CSS + Alpine.js (Frontend)
- SortableJS (Kanban drag-and-drop)
- SQLite (Local metadata)
- Qdrant (Vector DB, Docker)
- OpenAI API (GPT-5.2 + text-embedding-3-large)

## Quick Start

```bash
python run.py
```

This will check dependencies, start Qdrant via Docker, launch the web server and open `http://localhost:8000` in your browser.

## Setup

### Prerequisites

- Python 3.11 or higher
- Docker Desktop (for Qdrant)
- OpenAI API key

### Installation

1. Clone the repository
2. Install dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

3. Start Qdrant:

   ```bash
   docker-compose up -d
   ```

4. Set environment variables:
   ```bash
   export OPENAI_API_KEY=your_key_here
   ```

5. Run the application:
   ```bash
   python run.py
   ```

   Or directly:
   ```bash
   python -m src
   ```

### Running Tests

```bash
pytest
```

## Project Structure

```
src/
  web/                # FastAPI web application
    routers/          # API route handlers (chat, kanban, review, ingest, settings)
    templates/        # Jinja2 HTML templates
    static/           # CSS and static assets
  assistant/          # AI knowledge base module
    ingestion/        # Content extraction and synthesis
    retrieval/        # Vector search and RAG
    chat/             # Chat service
    storage/          # SQLite repositories
  kanban/             # Operational tracking module
    storage/          # Kanban DB
  shared/             # Common utilities (app state, client manager, logging, errors)
tests/                # Test suite (224 tests)
run.py                # Launcher script
```

## Data Isolation

All data is physically separated by client:

```
data/
  app.sqlite                    # Global config
  standard/
    assistant_kb.sqlite         # Standard knowledge
    uploads/
  clients/
    <CLIENT_CODE>/
      assistant_kb.sqlite       # Client knowledge
      uploads/
      kanban.sqlite             # Client Kanban
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/chat` | Chat page |
| POST | `/api/chat/send` | Send question (SSE stream) |
| GET | `/kanban` | Kanban board |
| GET/POST | `/api/kanban/tickets` | List/create tickets |
| PUT | `/api/kanban/tickets/{id}/move` | Move ticket (drag-drop) |
| GET | `/review` | Review page |
| POST | `/api/review/items/{id}/approve` | Approve + index KB item |
| GET | `/ingest` | Ingest page |
| POST | `/api/ingest/text` | Ingest text content |
| POST | `/api/ingest/file` | Upload PDF/DOCX |
| GET | `/settings` | Settings page |
| POST | `/api/settings/client` | Register client |

## Development

See `PRACTICES.md` for engineering rules and workflow.

## Current Status

- [x] M0: Repo setup, CI, Qdrant Docker
- [x] M1: Client manager + storage layout
- [x] M2: Assistant SQLite repos (KB items + ingestions, dedupe, versioning)
- [x] M3: Qdrant integration (collections, upsert, search)
- [x] M4: Document extraction (Text, PDF, DOCX)
- [x] M5: OpenAI synthesis pipeline (structured outputs, validation, retry)
- [x] M6: Assistant chat RAG (embedding, retrieval, answer, traceability)
- [x] M7: Kanban module (CRUD, history, independent DB)
- [x] Web migration: FastAPI + Tailwind CSS + Alpine.js + SortableJS
