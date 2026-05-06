# Developer Guide

## Setup

```bash
pip install -e .[dev]
docker compose up -d
python run.py
```

## Configuration

Set `OPENAI_API_KEY` through environment, `.env` or Settings. Qdrant defaults to `http://localhost:6333`.

## Project Structure

- `src/web`: FastAPI app, routers and templates.
- `src/assistant`: KB, ingestion, retrieval and chat.
- `src/incidents`: incident evidence and IP Box PDF dossier.
- `src/research`: SAP IS-U research agents.
- `src/ipbox`: usage logging and monthly reporting.
- `tests`: regression and feature tests.

## Adding Clients

Use Settings UI. Client-specific data is stored under `data/clients/<CLIENT_CODE>/`.

## Regenerating Embeddings

Approve and index KB items through Ingesta review. Bulk approval is available for drafts.

## Running Tests

```bash
pytest -q
```

For focused IP Box logging tests:

```bash
pytest -q tests/test_ipbox_usage_reporting.py
```

## Reports

Usage logs are read from `data/ip_box/usage_logs/`. Reports are written to `reports/ip_box/YYYY-MM/`.
