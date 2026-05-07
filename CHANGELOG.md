# Changelog

## v0.6.1 (2026-05-07)

### English Documentation

- Rewrote `README.md` in English with a product-oriented structure, architecture overview, endpoint summary, research-agent instructions, IP Box evidence usage logging examples and compliance notes.
- Rewrote `CHANGELOG.md` in English to remove mixed-language release notes and improve advisor/developer readability.

### Technical IP Dossier

- Added a product-level Technical IP Dossier in English under `docs/ip_box/00_technical_ip_dossier/`.
- Added both Markdown source and generated PDF:
  - `TECHNICAL_IP_DOSSIER.md`
  - `TECHNICAL_IP_DOSSIER.pdf`
- The dossier covers product overview, problem solved, custom software elements, technical architecture, AI boundary, third-party IP boundary, data isolation, evidence model, current implementation status, planned/TBC items and roadmap.
- The document explicitly distinguishes the proprietary software layer from SAP, OpenAI, Qdrant, public sources and client confidential data.

## v0.6.0 (2026-05-06)

### IP Box Evidence Pack

- Added a complete advisor-facing documentation pack under `docs/ip_box/` for assessing SAP IS-U Assistant as a potential copyrighted software asset.
- Added position paper, IP asset identification, technical architecture, software development/R&D report, development evidence index, technical decisions, source code inventory, third-party IP boundary, knowledge-base provenance, internal operating procedure, usage logging specification, ticket-level evidence templates, monthly report template, economic attribution methodology, service-line definition, revenue mapping, transfer-pricing/valuation input, productivity benchmark, QA evidence, data protection controls, user/developer guides, roadmap, management notes template and advisor pack index.
- The documentation distinguishes implemented functionality, planned/TBC work and factual evidence still to be collected.
- The pack avoids fabricated evidence: no invented commits, dates, screenshots, usage logs, hours or tickets.
- Added `AGENTS.md` with project-specific instructions for future AI coding agents.

### Usage Logging and Monthly Reporting

- Added `src/ipbox/usage_logging.py` for usage ID generation, query/response hashing, usage event validation and monthly JSONL usage logs.
- Added `src/ipbox/reporting.py` for monthly aggregation, preliminary attribution calculation, Markdown/CSV report generation and revenue mapping template export.
- Added `reports/templates/revenue_mapping_template.csv`.
- Added `tests/test_ipbox_usage_reporting.py` covering usage ID generation, log save/read, namespace preservation, attribution formula, monthly report generation and revenue mapping template creation.
- Updated app version to `v0.6.0`.

## v0.5.0 (2026-05-06)

### SAP IS-U Research Agents

- Added a controlled pipeline for turning external SAP IS-U references into KB candidates.
- Added a source registry with prioritized sources: SAP Help, SAP Learning, SAP Community Utilities, SAP Business Accelerator Hub, SAP Datasheet, LeanX, TCodeSearch, SE80, Michael Management, BDEW/EDI@Energy, SAP PRESS/Rheinwerk and specialized context sources.
- Added regulator sources: CNMC Spain, Utility Regulator Northern Ireland, Ireland Retail Market Design Service and CRE France.
- Added candidates with KB type, tags, SAP objects, signals, source metadata, confidence, copyright risk and automatic audit status.
- Added automatic promotion to KB DRAFT and optional auto-approval/indexing for low-risk candidates.
- Added the Indexer agent. If Qdrant/OpenAI indexing fails, the item remains in DRAFT for manual review.
- Added persistent research runs with Collector, Normalizer, Auditor, Ingestor and Indexer statuses.
- Added a curated SAP IS-U topic catalog with 145 topics covering transactions, navigation, customizing/SPRO, error messages, ABAP/BAdIs/exits, troubleshooting runbooks, MaKo, S/4HANA Utilities/Fiori/API and country rules.
- Added direct adapters for selected SAP Help topics and country/regulator packs.
- Added PDF extraction with `pypdf` for public regulator and market-message documents.
- Added autonomous crawler runs, crawler events and discovered topic persistence.

### Knowledge Types

- Added KB types for SAP technical content:
  - `SAP_TABLE`
  - `SAP_TRANSACTION`
  - `SAP_PROGRAM`
  - `SAP_MESSAGE`
  - `SAP_API`
  - `SAP_PROCESS`
  - `TECHNICAL_OBJECT`
  - `MARKET_PROCESS`
  - `EDIFACT_SPEC`
- Updated structured synthesis schema and prompt handling for the new types.

### UI and API

- Added SAP IS-U Research Candidates to the Ingesta page.
- Added Research Agent Runs dashboard with event timelines.
- Added starter topics for common SAP IS-U objects.
- Added Run Full Catalog workflow.
- Added Autonomous Source Crawler UI.
- Added Approve & Index All for KB drafts.
- Added collapsible/filterable long lists in Ingesta.
- Hid approval/index controls for already approved items while keeping Reject available.
- Forced research/crawler output into Standard KB; client-specific knowledge remains manual.
- Added research API endpoints for sources, candidates, runs, crawler runs, discovered topics and catalog runs.

### Tests

- Added tests for source registry, candidate normalization, SAP object detection, deduplication, KB draft promotion, reference-only source blocking, orchestration, catalog runs, crawler persistence, discovered topics, auto-indexing and UI controls.

## v0.4.0 (2026-05-04)

### SAP IS-U Incidents and IP Box Evidence

- Added the Incidencias module for client-isolated SAP IS-U technical incidents.
- Added `data/clients/<CLIENT_CODE>/incidents.sqlite`.
- Added incident evidence as file, link or note, with SHA256 for uploaded files.
- Added pages:
  - `/incidents`
  - `/incidents/{id}`
  - `/ipbox/dossier`
- Added CRUD APIs for incidents and evidence.
- Added incident-to-KB draft generation.
- Added annual English IP Box evidence dossier PDF based on incidents and hours.
- The dossier is an evidence pack and does not calculate Cyprus tax outcomes, QE/OE, nexus fraction or tax savings.

### Assistant and Ingesta

- Moved KB draft review into Ingesta; `/review` remains as a legacy route.
- Incident-generated KB entries remain DRAFT until approved.
- Fixed strict synthesis schema handling for `signals`.
- Added `.env` and Settings-based OpenAI API key loading.
- Updated chat messages to direct users to Ingesta review when no relevant knowledge is found.

### Kanban

- Added bulk close all tickets.
- Added bulk delete closed tickets.
- Preserved automatic cleanup of old closed tickets.
- Updated Kanban UI with bulk action buttons.

### Chat and UI

- Added visible delete controls for the active chat and chat sessions.
- Added explicit search/clear controls and result counts to Incidents.
- Updated navigation with Incidents and IP Box.

### Tests

- Added tests for incident repository/API/PDF generation, client isolation, evidence and KB drafts.
- Added tests for `.env` and synthesis schema behavior.
- Added tests for Kanban bulk actions and UI controls.
- Ran the main Assistant/Kanban/Finance non-OCR-heavy regression suites.

## v0.3.0 (2026-02-13)

### Finance

- Added finance settings, company data and tax rate configuration.
- Added expense categories with CRUD, reorder, activation/deactivation and delete protection.
- Added expenses with period, category, amount, merchant, notes, documents and document-not-required flag.
- Added invoices with line items, subtotal/VAT/total calculation and PENDING/PAID states.
- Added invoice PDF generation.
- Added monthly and yearly finance summaries.
- Added document upload/download, SHA256 hashing and expense linking.
- Added OCR extraction from PDFs/images.
- Added CSV exports for expenses and invoices.
- Added bulk expense import.
- Added bulk invoice import.
- Added Mark All Paid.
- Added Net Personal and Net Business summary views.
- Added consistent finance tab navigation.
- Improved dark mode and table alignment.

### Kanban Enhancements

- Made `ticket_id` editable with uniqueness validation.
- Added description field.
- Added stale ticket alerts.
- Unified create/edit modals.
- Added client dropdown in ticket modals.
- Improved drag/drop payload handling.
- Added client_code handling to history/delete endpoints.

### Tests

- Added a comprehensive test suite covering ingest, review, settings, client management, KB repository, chat repository, Kanban, finance edge cases, E2E flows, input validation and error handling.

## v0.2.3 (2026-02-11)

### Kanban Bugfixes

- Added frontend error handling for create, save and delete actions.
- Hardened backend client validation for Kanban repositories.

## v0.2.2 (2026-02-11)

### Kanban Ticket Creation

- Added plus button per Kanban column.
- Required client selection when creating tickets.
- Allowed explicit `client_code` in ticket creation.
- Added validation for invalid clients.
- Added default status handling when status is empty.

### Tests

- Added tests for explicit client creation, session fallback, invalid client, explicit status and empty status.

## v0.2.1 (2026-02-11)

### Assistant Scope and Retrieval

- Added explicit scopes: General, Client, Client + Standard.
- Added token gating when retrieval returns no usable context.
- Added validation that only APPROVED SQLite items are used after Qdrant retrieval.
- Added `model_called` audit flag.
- Added KB type filter in chat.
- Added deterministic ranking boost based on tags and SAP objects.

### Chat History

- Added persistent chat sessions.
- Added sidebar search, pin, rename, export and delete.
- Added configurable retention for old unpinned sessions.

### API

- Added chat session endpoints for list, create, messages, rename, pin, delete, export and retention.

### Tests

- Added integration and E2E tests for token gating, scope isolation, Qdrant routing, type filtering, ranking boost, chat sessions, retention, search, pin, rename, export and API endpoints.

## v0.2.0 (2026-02-10)

### UI and Kanban

- Added adaptive Kanban columns.
- Added Markdown rendering in notes.
- Added collapsible sidebar.
- Improved drag-and-drop highlighting.
- Added empty states.
- Added responsive design.
- Added priority border colors.
- Replaced Tailwind CDN with compiled CSS.
- Added ticket delete.
- Added priority filter.
- Added relative dates.
- Added priority counters.
- Added CSV export.
- Added global search.
- Added editable tags and links.
- Added ticket history in modal.
- Added server-side pagination.

### Backend

- Added persistent session secret in `data/.session_key`.
- Added delete ticket endpoint.
- Added Kanban CSV export endpoint.
- Added server-side search and pagination.
- Added tag/link update support.

### Tests

- Added integration tests for delete, search, pagination, priority filter, tags/links, export CSV, columns, history and session persistence.

## v0.1.0

- Initial release with Kanban board, Assistant RAG, Review, Ingest and Settings.
- Added eight colored Kanban status columns.
- Added CSV bulk import.
- Added streaming chat.
- Added dark mode.
