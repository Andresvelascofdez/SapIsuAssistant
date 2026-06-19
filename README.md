# SAP IS-U Assistant

SAP IS-U Assistant is a local, AI-assisted technical workbench for SAP IS-U consulting. It combines a structured knowledge base, RAG chat, semantic retrieval, incident registration, client-isolated evidence storage, research agents, recruitment support, Kanban operations, finance utilities and IP Box evidence reporting.

The tool is implemented as company-developed internal software with an external LLM provider. Its differentiating value is in the orchestration layer, SAP IS-U data model, client namespace separation, structured knowledge workflow, incident evidence model, research pipeline, review/indexing controls and reporting assets around software-enabled SAP IS-U technical delivery.

## Key Capabilities

### Assistant and RAG

- Retrieval Augmented Generation over approved knowledge base items.
- OpenAI embeddings with Qdrant vector search.
- Scope-aware retrieval:
  - General / Standard KB.
  - Client-only KB.
  - Client + Standard KB.
- Token gating: the LLM is not called when no relevant retrieval results exist.
- KB type filtering for incident patterns, root causes, resolutions, verification steps, customizing notes, ABAP notes, glossary entries, runbooks and SAP technical objects.
- Deterministic ranking boost for matching tags and SAP objects.
- Streaming chat responses with source/audit side panel.
- Persistent chat sessions with search, pin, rename, delete and export to Markdown/JSON.
- Configurable chat retention for old unpinned sessions.

### Knowledge Ingestion and Review

- Text, PDF and DOCX ingestion.
- Structured synthesis through OpenAI.
- KB draft workflow: generated knowledge remains in DRAFT until approved.
- Ingesta page integrates review and approval controls.
- Edit title, Markdown content, tags and SAP objects before approval.
- Approve and index one item or bulk approve/index all current drafts.
- Approved items are indexed into Qdrant; rejected items can be removed from retrieval.

### SAP IS-U Research Agents

- Controlled SAP IS-U research workflow:
  - Topic Scout.
  - Collector.
  - Normalizer.
  - Auditor.
  - Ingestor.
  - Indexer.
- Persistent run and crawler timelines with counters.
- Source registry with prioritized technical sources:
  - SAP Help.
  - SAP Learning.
  - SAP Community Utilities.
  - SAP Business Accelerator Hub.
  - SAP Datasheet.
  - LeanX.
  - TCodeSearch.
  - SE80.
  - Michael Management SAP messages.
  - BDEW / EDI@Energy.
  - CNMC Spain.
  - Utility Regulator Northern Ireland.
  - Ireland Retail Market Design Service.
  - CRE France.
  - SAP PRESS / Rheinwerk as reference-only.
- Expanded SAP IS-U topic catalog covering:
  - Master data.
  - Device management.
  - Meter reading.
  - Billing and invoicing.
  - FI-CA.
  - Move-in / move-out.
  - IDoc / IDE.
  - MaKo / EDIFACT.
  - BPEM / EMMA.
  - Transactions and navigation.
  - Customizing / SPRO.
  - Messages and errors.
  - ABAP, BAdIs, exits and APIs.
  - S/4HANA Utilities / Fiori / API.
  - Country market rules.
- Direct source adapters for selected SAP Help and regulator topics.
- PDF extraction for public regulator and market-message documents.
- Research/crawler-generated knowledge is always stored in Standard KB; client-specific knowledge must be ingested manually into the correct client scope.

### SAP IS-U Incidents and IP Box Evidence

- Client-isolated incident storage under `data/clients/<CLIENT_CODE>/incidents.sqlite`.
- Incident fields for SAP module, process, SAP objects, affected IDs, problem, technical uncertainty, investigation, solution, implementation notes, verification, outcome and reusable knowledge.
- Evidence attachments as files, links or notes.
- SHA256 hashing for uploaded evidence files.
- IP Box relevance classification:
  - `UNCLEAR`
  - `QUALIFYING_CANDIDATE`
  - `NOT_QUALIFYING`
- Incident-derived KB drafts remain in DRAFT until approved.
- Annual English IP Box incident evidence dossier PDF.
- The dossier is an evidence pack only. It does not calculate Cyprus eligibility, QE/OE, nexus fraction, qualifying profit, tax savings or final tax treatment.

### IP Box Evidence Pack

- Advisor-facing documentation under `docs/ip_box/`.
- Technical IP Dossier source and generated PDF under `docs/ip_box/00_technical_ip_dossier/`.
- Position paper, IP asset identification, architecture, R&D/development report, source inventory, third-party IP boundary, KB provenance, internal operating procedure, usage logging specification, ticket-level evidence templates, monthly report template, economic attribution methodology, service-line definition, revenue mapping, TP/valuation input, productivity benchmark, QA evidence, data protection controls, user/developer guides, roadmap and advisor pack index.
- Modular backend usage logging in `src/ipbox/usage_logging.py`.
- Monthly usage reporting and CSV export in `src/ipbox/reporting.py`.
- IP evidence review UI at `/ipbox/usage` for real recorded usage events.
- Automatic usage evidence logging for priority workflows: RAG chat, incident registration, incident-to-KB, KB approval/indexing, research-agent promotion/indexing and dossier generation.
- Revenue mapping template in `reports/templates/revenue_mapping_template.csv`.
- Factual evidence stance:
  - Do not invent commits, dates, screenshots, usage logs, hours, tickets or client evidence.
  - Mark incomplete items as TBC or planned.
  - Final IP Box treatment must be reviewed by qualified Cyprus tax advisors.

### Kanban

- Client-isolated Kanban ticket board.
- Drag-and-drop status columns.
- Configurable columns.
- Ticket IDs, title, description, priority, notes, tags and links.
- Search, priority filtering and CSV import/export.
- Ticket history.
- Bulk close all tickets.
- Bulk delete closed tickets.
- Automatic cleanup of old closed tickets.

### Recruitment

- Simple candidate and CV database under `data/recruitment/candidates.db`.
- Original CV storage under `data/recruitment/cvs/`.
- PDF, legacy DOC, DOCX and TXT CV import with local text extraction.
- DOCX table extraction for CVs whose personal data is stored inside Word tables.
- Rule-based CV autofill for name, email, phone, LinkedIn, main role, seniority, years of experience, rates and currency.
- CV autofill handles split LinkedIn URLs, Spanish contact labels, language sections, country inference from location/phone clues and profile-level experience statements.
- Email, phone or LinkedIn is accepted as the minimum candidate contact evidence; missing contact details must be completed manually.
- Manual save workflow: importing a CV opens a prefilled candidate form but does not create a candidate until the user saves it.
- Candidate edit form can replace the stored CV path and extracted text without deleting older CV files.
- Candidate list pagination avoids long unbounded scrolling in filtered and unfiltered views.
- Candidate edit modal keeps clicks on the backdrop from closing the form or selecting rows behind it.
- Editable candidate forms support previous/next navigation across the current result set.
- Search across candidate fields and extracted CV text.
- Combinable filters for skill text, SAP module text, language text, country, seniority, work mode and maximum hourly/daily rate.
- No ranking, matching score, candidate pipeline, availability tracking, margin calculation, profit estimation or AI-generated candidate scoring in this version.

### Finance

- Personal/business finance support module.
- Expense categories and documents.
- Invoice creation, line items and PDF generation.
- Monthly/yearly summary.
- Net Personal and Net Business views.
- OCR support for PDFs/images.
- Bulk expense and invoice import.
- Mark all invoices paid.
- CSV export.

### Settings

- Client registry.
- Active client selector.
- Standard KB toggle.
- Qdrant URL configuration.
- OpenAI API key from environment, `.env` or Settings.
- Dark mode.

## Architecture

```text
Local Browser UI
    |
FastAPI Routers
    |
    +-- Assistant / Chat / Ingesta
    |       +-- SQLite KB repositories
    |       +-- OpenAI embeddings and chat
    |       +-- Qdrant vector retrieval
    |
    +-- Incidents
    |       +-- Client incident SQLite
    |       +-- Evidence files / links / SHA256
    |       +-- Annual IP Box PDF dossier
    |
    +-- Research Agents
    |       +-- Source registry
    |       +-- Topic catalog
    |       +-- Candidate audit
    |       +-- KB draft promotion and indexing
    |
    +-- IP Box Evidence
    |       +-- Usage evidence review UI
    |       +-- JSONL usage logs
    |       +-- Monthly Markdown/CSV reports
    |
    +-- Recruitment
    |       +-- Candidate SQLite database
    |       +-- CV file storage and local parsing
    |       +-- Rule-based form autofill
    |
    +-- Kanban / Finance / Settings
```

## Technology Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Frontend | Jinja2, Tailwind CSS, Alpine.js, SortableJS |
| Metadata | SQLite |
| Vector database | Qdrant |
| AI | OpenAI API, `text-embedding-3-large` |
| PDF | ReportLab, pypdf |
| OCR | pytesseract, Pillow |
| Infrastructure | Docker Compose for Qdrant |

## Quick Start

```bash
python run.py
```

The launcher checks dependencies, starts Qdrant through Docker, starts the web server and opens `http://localhost:8000`.

## Installation

### Requirements

- Python 3.11+
- Docker Desktop for Qdrant
- OpenAI API key

### Steps

1. Install dependencies:

   ```bash
   pip install -e .[dev]
   ```

2. Start Qdrant:

   ```bash
   docker compose up -d
   ```

3. Configure the OpenAI API key:

   ```bash
   set OPENAI_API_KEY=<your-openai-api-key>
   ```

   You can also store it in `.env`:

   ```bash
   OPENAI_API_KEY=<your-openai-api-key>
   ```

   Or configure it from the Settings page.

4. Run the app:

   ```bash
   python run.py
   ```

## Project Structure

```text
src/
  web/
    app.py
    dependencies.py
    routers/
      chat.py
      ingest.py
      review.py
      kanban.py
      incidents.py
      research.py
      recruitment.py
      finance.py
      settings.py
    templates/
      base.html
      chat.html
      ingest.html
      review.html
      kanban.html
      incidents.html
      incident_detail.html
      ipbox_dossier.html
      recruitment.html
      finance_*.html
      settings.html
  assistant/
    ingestion/
    retrieval/
    chat/
    storage/
  incidents/
    storage/
    pdf/
  research/
    agents/
    storage/
  ipbox/
    usage_logging.py
    reporting.py
  kanban/
  finance/
  shared/
core/
  recruitment/
    candidate_manager.py
    cv_parser.py
    cv_autofill.py
ui/
  recruitment/
    candidates_tab.py
    candidate_form.py
docs/
  ip_box/
reports/
  templates/
tests/
```

## Data Isolation

```text
data/
  app.sqlite
  chat_history.sqlite
  finance.sqlite
  standard/
    assistant_kb.sqlite
    uploads/
  clients/
    <CLIENT_CODE>/
      assistant_kb.sqlite
      kanban.sqlite
      incidents.sqlite
      incident_evidence/
      uploads/
  research/
    source_registry.sqlite
  recruitment/
    candidates.db
    cvs/
  ip_box/
    usage_logs/
  ipbox/
    dossiers/
reports/
  ip_box/
    YYYY-MM/
  templates/
```

Standard KB and client-specific KB are separate. Client incidents and uploaded evidence are stored per client. Qdrant uses a Standard collection and per-client collections.

## API Overview

### Chat and KB

| Method | Route | Description |
| --- | --- | --- |
| GET | `/chat` | Chat page |
| POST | `/api/chat/send` | Send question via SSE |
| GET | `/api/chat/sessions` | List sessions |
| POST | `/api/chat/sessions` | Create session |
| GET | `/api/chat/sessions/{id}/messages` | Session messages |
| PUT | `/api/chat/sessions/{id}/rename` | Rename session |
| PUT | `/api/chat/sessions/{id}/pin` | Pin/unpin session |
| DELETE | `/api/chat/sessions/{id}` | Delete session |
| GET | `/api/chat/sessions/{id}/export` | Export session |
| GET | `/ingest` | Ingestion and KB review |
| POST | `/api/ingest/text` | Ingest text |
| POST | `/api/ingest/file` | Ingest file |
| GET | `/api/review/items` | List KB items |
| POST | `/api/review/items/{id}/approve` | Approve and index |
| POST | `/api/review/items/bulk-approve` | Bulk approve and index |
| POST | `/api/review/items/{id}/reject` | Reject item |

### Research

| Method | Route | Description |
| --- | --- | --- |
| GET | `/api/research/sources` | List research sources |
| POST | `/api/research/sources/seed` | Seed default sources |
| GET | `/api/research/topic-catalog` | SAP IS-U topic catalog |
| POST | `/api/research/runs` | Start one research run |
| POST | `/api/research/runs/catalog` | Start catalog runs |
| GET | `/api/research/runs/{id}` | Run status |
| GET | `/api/research/runs/{id}/events` | Run timeline |
| POST | `/api/research/crawls` | Start autonomous crawler |
| GET | `/api/research/crawls/{id}` | Crawler status |
| GET | `/api/research/crawls/{id}/events` | Crawler timeline |
| GET | `/api/research/discovered-topics` | Discovered topics |
| POST | `/api/research/collect-url` | Collect one public URL |
| GET | `/api/research/candidates` | List candidates |
| POST | `/api/research/candidates/{id}/promote-to-kb-draft` | Promote candidate |
| POST | `/api/research/candidates/{id}/reject` | Reject candidate |

### Incidents and IP Box

| Method | Route | Description |
| --- | --- | --- |
| GET | `/incidents` | Incident list |
| GET | `/incidents/{id}` | Incident detail |
| GET | `/ipbox/dossier` | Annual dossier page |
| GET | `/ipbox/usage` | Monthly usage evidence review |
| GET | `/api/incidents` | List incidents |
| POST | `/api/incidents` | Create incident |
| GET | `/api/incidents/{id}` | Get incident |
| PUT | `/api/incidents/{id}` | Update incident |
| DELETE | `/api/incidents/{id}` | Delete incident |
| POST | `/api/incidents/{id}/evidence` | Add evidence |
| DELETE | `/api/incidents/{id}/evidence/{evidence_id}` | Delete evidence |
| POST | `/api/incidents/{id}/generate-kb-draft` | Create KB draft |
| POST | `/api/incidents/{id}/link-usage-event` | Link usage evidence |
| POST | `/api/incidents/{id}/mark-verified` | Mark incident as verified |
| GET | `/api/ipbox/dossier?year=YYYY` | Download annual PDF |
| GET | `/api/ipbox/usage-events` | List/filter usage events |
| PUT | `/api/ipbox/usage-events/{usage_id}` | Review/update usage event metadata |
| POST | `/api/ipbox/monthly-report` | Generate monthly evidence report |
| GET | `/api/ipbox/monthly-report/download` | Download monthly Markdown/CSV report |

### Kanban

| Method | Route | Description |
| --- | --- | --- |
| GET | `/kanban` | Kanban board |
| GET | `/api/kanban/tickets` | List tickets |
| POST | `/api/kanban/tickets` | Create ticket |
| PUT | `/api/kanban/tickets/{id}` | Update ticket |
| PUT | `/api/kanban/tickets/{id}/move` | Move ticket |
| DELETE | `/api/kanban/tickets/{id}` | Delete ticket |
| POST | `/api/kanban/tickets/bulk-close` | Close all tickets |
| DELETE | `/api/kanban/tickets/closed` | Delete closed tickets |
| POST | `/api/kanban/import-csv` | Import CSV |
| GET | `/api/kanban/export-csv` | Export CSV |

### Recruitment

| Method | Route | Description |
| --- | --- | --- |
| GET | `/recruitment` | Candidate database page |
| GET | `/api/recruitment/candidates` | List/search/filter candidates |
| POST | `/api/recruitment/candidates` | Create candidate |
| GET | `/api/recruitment/candidates/{id}` | Get candidate |
| PUT | `/api/recruitment/candidates/{id}` | Update candidate |
| DELETE | `/api/recruitment/candidates/{id}` | Delete candidate |
| POST | `/api/recruitment/cv/import` | Import PDF/DOCX/TXT CV and return autofill draft |
| POST | `/api/recruitment/candidates/{id}/open-cv` | Open stored CV file with the local OS default app |

### Finance and Settings

Finance routes cover expenses, invoices, uploads, OCR, summaries, CSV exports and invoice PDF generation. Settings routes cover clients, Qdrant URL, OpenAI API key, active client and Standard KB toggle.

## Running Research Agents

1. Open `http://localhost:8000/ingest`.
2. Use `Autonomous Source Crawler` for source discovery.
3. Select sources and seed queries.
4. Set `Pages/source` and `Max topics`.
5. Enable `Queue research runs`, `Promote drafts` and `Auto-index low-risk` for the full pipeline.
6. Click `Start Crawler`.
7. Monitor Topic Scout, Source Crawler, Topic Extractor and Run Queuer.

For the curated catalog, use `Run Full Catalog`. Existing KB items are deduplicated/versioned; a full reset is not required.

## Recruitment Usage

1. Open `http://localhost:8000/recruitment`.
2. Use `Import CV` to select a PDF, DOC, DOCX or TXT file.
3. Review the extracted text and rule-based autofill fields.
4. Save manually to create the candidate.
5. Use search and filters to find candidates by free text, skills, SAP module text, language, country, seniority, work mode or maximum rate.

The Recruitment module intentionally stores only candidate database fields and original CV paths. It does not perform AI matching, ranking, pipeline management, availability tracking or profitability calculations.

## IP Box Evidence Usage Logging

The application records hashed usage metadata for the priority workflows listed above. Raw prompts/responses are not stored by default; query and response hashes plus retrieval metadata are stored instead.

Review events from the UI:

1. Open `http://localhost:8000/ipbox/usage`.
2. Filter by month, client, SAP module/process, output use or delivery use.
3. Mark events as `reviewed`, `used` or `discarded`.
4. Add ticket/reference, notes and optional time estimates.
5. Export the monthly Markdown/CSV report.

Manual logging is also available for controlled internal workflows:

```python
from pathlib import Path
from src.ipbox.usage_logging import create_usage_record, save_usage_event

record = create_usage_record(
    user="consultant",
    active_client="CLIENT_A",
    ticket_reference="TCKXXXXX",
    task_type="RAG_CHAT",
    sap_module="IS-U",
    sap_isu_process="meter-reading",
    search_mode="COMBINED",
    sources_used="BOTH",
    manual_verification_status="TODO/TBC",
)
save_usage_event(Path("data"), record)
```

Generate a monthly report from reviewed real logs:

```python
from pathlib import Path
from src.ipbox.reporting import generate_monthly_ip_report

generate_monthly_ip_report(
    Path("data"),
    Path("reports"),
    "2026-05",
)
```

These reports are internal evidence for advisor review. They do not determine final IP Box eligibility or tax treatment.

## Technical IP Dossier

The main product-oriented IP dossier is available at:

- `docs/ip_box/00_technical_ip_dossier/TECHNICAL_IP_DOSSIER.md`
- `docs/ip_box/00_technical_ip_dossier/TECHNICAL_IP_DOSSIER.pdf`

It explains the product, problem solved, custom/innovative software elements, architecture, AI boundary, data controls, evidence model and roadmap.

## Tests

Run the main suite:

```bash
pytest -q
```

Focused tests:

```bash
pytest -q tests/test_research_pipeline.py
pytest -q tests/test_ipbox_usage_reporting.py
pytest -q tests/test_incidents.py
pytest -q tests/test_recruitment.py
pytest -q tests/test_ui_controls.py
```

Some finance/OCR tests are slower because they exercise OCR-heavy paths.

## Evidence and Compliance Notes

- Do not store client confidential content in Standard KB.
- Do not commit real candidate CVs, phone numbers, emails or recruitment records.
- Do not include raw client data in advisor packs without review and anonymisation.
- Do not invent evidence, dates, screenshots, usage logs, commits or time records.
- SAP, OpenAI, Qdrant and open-source dependencies are third-party components.
- The candidate proprietary IP is the company-developed software layer.
- Final Cyprus IP Box eligibility, qualifying profit, nexus fraction, attribution and tax treatment must be reviewed by qualified advisors.
