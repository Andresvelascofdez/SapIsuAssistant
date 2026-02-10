# SAP IS-U Assistant + Kanban (Centralized App) — Implementation Plan (Codex Spec)

## 1) Product Overview

This project contains **two independent modules** in one desktop app:

1. **Assistant (AI + Knowledge Base)**
   - You manually ingest knowledge (free text, PDF, DOCX, or any content you choose).
   - The app extracts text and sends it to OpenAI.
   - The model **synthesizes** the content into **structured knowledge items** (KB items) following a strict JSON schema.
   - You review/approve the KB items.
   - Only approved KB items are indexed in **Qdrant** and used for RAG in the assistant chat.

2. **Kanban (Operational Ticket Board)**
   - Used only for operational tracking (status, priority, notes, links).
   - **Must not** feed the assistant knowledge base automatically.
   - Lives in its own tab, with its own database.

### Non-goals (explicit)
- No automatic ingestion from Kanban into KB.
- No cross-client data mixing (Assistant or Kanban).
- No “hidden” fallback search (Qdrant is required from day 1).
- No icons/emojis in UI or code strings.

---

## 2) Tech Stack (Fixed)

- Python 3.11+
- Desktop UI: Tkinter + ttkbootstrap
- Local metadata store: SQLite
- Vector DB: Qdrant (Docker, local)
- OpenAI API: Responses API
  - Chat + synthesis: `gpt-5.2` (reasoning enabled)
  - Embeddings: `text-embedding-3-large` (3072 dims)
- Testing: pytest
- CI: GitHub Actions (pytest)

---

## 3) Data Separation (Hard Guarantee)

All storage is physically separated by client.

```
data/
  app.sqlite                      # global config/settings
  standard/
    assistant_kb.sqlite
    uploads/
  clients/
    <CLIENT_CODE>/
      assistant_kb.sqlite
      uploads/
      kanban.sqlite
```

### Rules
- Assistant uses:
  - `data/standard/assistant_kb.sqlite` (optional enable/disable)
  - `data/clients/<ACTIVE_CLIENT>/assistant_kb.sqlite`
- Kanban uses:
  - `data/clients/<ACTIVE_CLIENT>/kanban.sqlite`
- No module may open or query any other client folder than the active one.

---

## 4) Qdrant Design (Fixed)

### 4.1 Collections
- `kb_standard`
- `kb_<CLIENT_CODE>` (e.g., `kb_SWE`, `kb_HERON`)

### 4.2 Vector configuration
- Vector size: `3072` (embedding model default)
- Distance: `cosine`

### 4.3 Point identity
- Qdrant `point_id` = `kb_id` (UUID string)

### 4.4 Qdrant payload (minimum)
Store only metadata needed for filtering and traceability. Do **not** store full content.
Payload fields:
- `kb_id`
- `type`
- `title`
- `tags` (array)
- `sap_objects` (array)
- `client_scope` (`standard`|`client`)
- `client_code` (null for standard)
- `version` (int)
- `updated_at` (ISO string)

### 4.5 Indexing rules
- Only KB items with status `APPROVED` are indexed in Qdrant.
- When a KB item is updated and re-approved:
  - Increment `version`
  - Upsert the new vector in Qdrant using the same `kb_id` and updated payload.

### 4.6 Query rules
- Retrieval always queries:
  - `kb_standard` (if enabled) + `kb_<ACTIVE_CLIENT>`
- Never query other client collections.

---

## 5) Local Storage (SQLite) — Assistant (Source of Truth)

SQLite is the **source of truth** for KB items, versioning, dedupe, and approvals.

### 5.1 Tables (Assistant KB)

**`kb_items`**
- `kb_id TEXT PRIMARY KEY`
- `client_scope TEXT NOT NULL`              # standard | client
- `client_code TEXT NULL`                   # required when client_scope=client
- `type TEXT NOT NULL`                      # from the fixed enum
- `title TEXT NOT NULL`
- `content_markdown TEXT NOT NULL`
- `tags_json TEXT NOT NULL`
- `sap_objects_json TEXT NOT NULL`
- `signals_json TEXT NOT NULL`              # additional metadata (module/process/etc.)
- `sources_json TEXT NOT NULL`              # input provenance (hash, filename, etc.)
- `version INTEGER NOT NULL`
- `status TEXT NOT NULL`                    # DRAFT | APPROVED | REJECTED
- `content_hash TEXT NOT NULL`              # sha256(content_markdown + title + type)
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

**`ingestions`**
- `ingestion_id TEXT PRIMARY KEY`
- `client_scope TEXT NOT NULL`
- `client_code TEXT NULL`
- `input_kind TEXT NOT NULL`                # text | pdf | docx
- `input_hash TEXT NOT NULL`                # sha256(raw extracted text)
- `input_name TEXT NULL`                    # filename or label
- `status TEXT NOT NULL`                    # DRAFT | SYNTHESIZED | FAILED | APPROVED | REJECTED
- `model_used TEXT NOT NULL`
- `reasoning_effort TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

**Dedupe rule (KB items)**
- If same `type + normalized_title` and same `content_hash` exists in the same scope (standard or the same client):
  - Do not create a duplicate record.
- If same `type + normalized_title` but different `content_hash`:
  - Create a new version (increment `version`).

---

## 6) Local Storage (SQLite) — Kanban (Independent)

**`tickets`**
- `id TEXT PRIMARY KEY`
- `ticket_id TEXT`
- `title TEXT NOT NULL`
- `status TEXT NOT NULL`
- `priority TEXT NOT NULL`
- `notes TEXT`
- `links_json TEXT NOT NULL`
- `tags_json TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `closed_at TEXT NULL`

**`ticket_history`**
- `id TEXT PRIMARY KEY`
- `ticket_id TEXT NOT NULL`
- `from_status TEXT`
- `to_status TEXT NOT NULL`
- `changed_at TEXT NOT NULL`

---

## 7) Knowledge Types (Fixed Enum)

KB item `type` must be one of:
- `INCIDENT_PATTERN`
- `ROOT_CAUSE`
- `RESOLUTION`
- `VERIFICATION_STEPS`
- `CUSTOMIZING`
- `ABAP_TECH_NOTE`
- `GLOSSARY`
- `RUNBOOK`

---

## 8) Ingestion Pipeline (Assistant)

### 8.1 Inputs supported
- Free text (pasted)
- PDF
- DOCX

### 8.2 Extraction
- Extracted text is processed in-memory.
- The app computes `input_hash = sha256(extracted_text)`.
- The raw file (PDF/DOCX) may be saved only in:
  - `data/standard/uploads/` or `data/clients/<CLIENT>/uploads/`
  using a stable hash-based filename (no temp names).

### 8.3 Synthesis call (OpenAI)
- Model: `gpt-5.2`
- Reasoning effort: `xhigh`
- Output: strict JSON (see schema below)
- The app validates JSON against schema:
  - If invalid: 1 controlled retry
  - If still invalid: mark ingestion as `FAILED`

### 8.4 Review & approve
- UI shows synthesized KB items.
- User can edit fields.
- On approve:
  - Save KB items to SQLite with status `APPROVED`
  - Embed and upsert into Qdrant

---

## 9) Structured Output Schema (Synthesis)

Synthesis must return:

```json
{
  "kb_items": [
    {
      "type": "RUNBOOK",
      "title": "Short title",
      "content_markdown": "Markdown content",
      "tags": ["IDEX", "UTILMD", "MaKo"],
      "sap_objects": ["EDATEXMON01", "/IDXGC/PDOCMON01", "EDEXPROC"],
      "signals": {
        "module": "IDEX",
        "process": "GPKE",
        "country": "DE"
      }
    }
  ]
}
```

Validation rules:
- `kb_items` is non-empty
- `type` must match enum
- `title`, `content_markdown` non-empty
- arrays must be arrays of strings
- `signals` is an object (may be empty)

---

## 10) Assistant Chat (RAG)

### 10.1 Retrieval (Qdrant)
- Embed the user question with `text-embedding-3-large`
- Query Qdrant:
  - `kb_standard` (if enabled) and `kb_<ACTIVE_CLIENT>`
- Top-K default: 8
- Fetch the corresponding KB items from SQLite by `kb_id`

### 10.2 Answer call (OpenAI)
- Model: `gpt-5.2`
- Reasoning effort:
  - default `high`
  - optional toggle `xhigh`
- The prompt includes:
  - user question
  - retrieved KB items as “context pack”
  - hard constraints:
    - do not reference Kanban
    - do not assume facts not supported by context
    - list “missing inputs” if needed

### 10.3 Traceability
- UI shows which KB items were used (titles + ids).

---

## 11) UI (Tabs)

Top bar:
- Active client dropdown
- Standard KB enabled toggle
- Buttons: `Ingest Knowledge`, `Assistant`, `Kanban`, `Settings`

Tabs:
1. **Assistant Chat**
2. **Knowledge Ingest**
3. **Knowledge Review (queue of ingestions)**
4. **Knowledge Search (optional, later)**
5. **Kanban**
6. **Settings**

---

## 12) Configuration & Secrets

- OpenAI API key is loaded from environment (`OPENAI_API_KEY`) or OS keychain (optional future).
- Qdrant URL: default `http://localhost:6333`
- Data directory root: configurable (default `./data/`)

No secrets are committed to git.

---

## 13) Milestones (Execution Order)

### M0 — Repo + CI + Qdrant Docker
- Create repo structure
- Add `docker-compose.yml` for Qdrant
- Add pytest + GitHub Actions workflow

Acceptance:
- `pytest` passes
- Qdrant healthcheck reachable locally

### M1 — Client Manager + Storage Layout
- `app.sqlite` with clients + settings
- Create client folders and DBs on demand

Acceptance:
- unit test verifying strict folder/DB isolation

### M2 — Assistant SQLite Repos + KB Item CRUD
- Implement `kb_items` + `ingestions` repositories
- Implement dedupe/versioning rules

Acceptance:
- tests for dedupe and version increments

### M3 — Qdrant Integration (Collections + Upsert + Search)
- Create collections if missing
- Upsert approved KB items
- Search returns kb_ids

Acceptance:
- integration tests (optional) / mocked unit tests

### M4 — Extraction (Text/PDF/DOCX)
- Extractors with deterministic output
- Store uploads by hash if needed

Acceptance:
- tests using tmp_path only

### M5 — OpenAI Synthesis Pipeline (Structured Outputs)
- Call Responses API, validate schema
- Write synthesized drafts to SQLite
- Review UI + approve workflow
- Approve triggers embedding + Qdrant upsert

Acceptance:
- schema validation tests
- end-to-end test with OpenAI mocked

### M6 — Assistant Chat RAG
- Embed question
- Qdrant retrieval
- Answer call with context pack
- Traceability shown in UI

Acceptance:
- test ensures only standard + active client collections queried

### M7 — Kanban (Independent)
- Kanban SQLite + UI board + CRUD + history

Acceptance:
- tests confirm Kanban uses its own DB and never queries assistant DB

---

## 14) Repo Layout (Fixed)

```
src/
  assistant/
    ingestion/
    retrieval/
    chat/
    storage/
  kanban/
    storage/
    ui/
  shared/
tests/
.github/workflows/
```

---

## 15) Hard Constraints Summary (Must Follow)

- Qdrant required from day 1 (no fallback retrieval)
- SQLite is the source of truth for KB items and ingestions
- Only APPROVED KB items are indexed in Qdrant
- Kanban is independent and never used as assistant knowledge
- Strict client separation by physical storage paths
- No icons/emojis in UI or code strings
