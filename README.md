# SAP IS-U Assistant + Kanban

A desktop application providing AI-powered knowledge management and operational tracking for SAP IS-U systems.

## Features

- **Assistant Module**: AI-powered knowledge base with RAG (Retrieval Augmented Generation)
  - Ingest knowledge from text, PDF, DOCX
  - Structured synthesis using OpenAI GPT-5.2
  - Client-isolated knowledge bases
  - Vector search via Qdrant

- **Kanban Module**: Operational ticket tracking
  - Status, priority, notes, links
  - Independent from assistant knowledge base
  - Client-isolated boards

## Tech Stack

- Python 3.11+
- Tkinter + ttkbootstrap (Desktop UI)
- SQLite (Local metadata)
- Qdrant (Vector DB, Docker)
- OpenAI API (GPT-5.2 + embeddings)

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

### Running Tests

```bash
pytest
```

## Project Structure

```
src/
  assistant/          # AI knowledge base module
    ingestion/        # Content extraction and synthesis
    retrieval/        # Vector search and RAG
    chat/             # Chat interface
    storage/          # SQLite repositories
  kanban/             # Operational tracking module
    storage/          # Kanban DB
    ui/               # Kanban board UI
  shared/             # Common utilities
tests/                # Test suite
.github/workflows/    # CI/CD
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

## Development

See `PRACTICES.md` for engineering rules and workflow.
See `PLAN.md` for detailed implementation plan.

## Current Status

- [x] M0: Repo setup, CI, Qdrant Docker
- [x] M1: Client manager + storage layout
- [x] M2: Assistant SQLite repos (KB items + ingestions, dedupe, versioning)
- [x] M3: Qdrant integration (collections, upsert, search)
- [ ] M4: Document extraction
- [ ] M5: OpenAI synthesis pipeline
- [ ] M6: Assistant chat RAG
- [ ] M7: Kanban module
