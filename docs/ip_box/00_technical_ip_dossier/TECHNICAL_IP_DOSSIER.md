# Technical IP Dossier

SAP IS-U Assistant

Document date: 2026-05-07

Document purpose: product-level technical dossier for advisor review.

Important limitation: this document describes the proprietary software layer and the evidence model around the tool. It does not determine Cyprus IP Box eligibility, qualifying expenditure, overall expenditure, nexus fraction, qualifying profits, tax savings, transfer pricing, legal ownership or filing treatment. Those matters must be reviewed by qualified Cyprus tax and legal advisors using factual records.

<!-- pagebreak -->

# Document Control

## Product

SAP IS-U Assistant is a local, AI-assisted technical workbench for SAP IS-U consulting. It combines semantic search, structured knowledge management, SAP IS-U incident registration, client-isolated storage, controlled knowledge ingestion, research agents, RAG chat, Kanban support, finance utilities and IP Box evidence reporting.

## Qualifying asset under review

The asset under review is the original software layer developed for SAP IS-U Assistant. This includes source code, architecture, data models, workflow logic, prompt/orchestration logic, user interface flows, namespace filtering, review/indexing controls, incident evidence structures, research-agent workflows, usage logging and reporting modules, tests and company-authored documentation.

## Items explicitly outside the owned IP boundary

- SAP software, SAP IS-U itself, SAP standard tables, SAP transactions, SAP messages, SAP programs and SAP documentation.
- OpenAI models and API services.
- Qdrant and other third-party infrastructure or open-source dependencies.
- Third-party public web content.
- Client confidential data and client-specific business facts.
- Tax conclusions and legal conclusions.

## Evidence stance

This dossier must not be used to invent evidence. Development dates, commit history, screenshots, usage logs, tickets, hours, invoices and client examples must come from real records. Where functionality is planned or partial, this document marks it as planned, partial or TBC.

<!-- pagebreak -->

# Executive Summary

SAP IS-U Assistant is intended to turn SAP IS-U consulting know-how into a governed, reusable, client-isolated software workflow. The product addresses a common problem in utility consulting: technical knowledge is spread across prior tickets, SAP objects, screenshots, consultant notes, public references, client-specific Z objects, market communication rules and individual memory. This creates repeated analysis, inconsistent ancliars, weak traceability and higher risk of mixing confidential client knowledge with generic SAP knowledge.

The tool solves this by providing a structured knowledge base, semantic retrieval, RAG chat, SAP IS-U incident registration, evidence capture, controlled ingestion/review, autonomous Standard KB research agents, namespace-aware retrieval and advisor-facing evidence reports. The OpenAI model is only a provider. The proprietary value is the software layer that decides what is stored, how knowledge is classified, how retrieval scope is enforced, how incidents become governed knowledge, how research output is normalized, and how evidence can be reported.

For IP Box review, the strongest candidate asset is copyrighted software: the original application code and documentation around SAP IS-U Assistant. The tool may support a future evidence position that some SAP IS-U service income is materially assisted by proprietary software. That position requires factual usage logs, ticket references, output-used confirmation, monthly reports and advisor validation. The current repository includes the software modules, tests and documentation pack needed to start building that evidence.

<!-- pagebreak -->

# 1. Product Overview

## What the tool is

SAP IS-U Assistant is a specialist software product for SAP IS-U technical support and consulting. It is designed for a consultant who needs to retrieve, structure, reuse and evidence technical knowledge across SAP IS-U processes.

The product currently includes:

- A local browser-based desktop UI served by FastAPI.
- A client selector that determines the active knowledge namespace.
- A structured knowledge base with Standard and client-scoped records.
- OpenAI embeddings and Qdrant vector search for semantic retrieval.
- RAG chat with source/audit information.
- Ingestion of text, PDF and DOCX material.
- Review controls for generated KB drafts before they enter retrieval.
- SAP IS-U incident registration with evidence and SHA256 hashes for files.
- Incident-to-KB draft generation.
- Annual English incident evidence PDF generation for IP Box support.
- SAP IS-U research agents for Standard KB enrichment.
- Kanban workflow support.
- Finance utilities for operational administration.
- Backend usage logging and monthly report generation for IP evidence.

## Intended user

The intended user is a SAP IS-U consultant or technical lead who needs to ancliar questions, investigate incidents, prepare client responses, reuse previous learning and maintain a clear boundary between generic SAP IS-U knowledge and client-specific knowledge.

## Product surface

The main product surfaces are:

- Chat: semantic retrieval and AI-assisted technical ancliars.
- Ingesta: knowledge ingestion, review, approval, indexing and research-agent supervision.
- Incidencias: SAP IS-U incident capture, evidence and reusable knowledge generation.
- IP Box dossier: yearly incident evidence PDF.
- Kanban: operational task management.
- Finance: expense/invoice support.
- Settings: client selection, OpenAI key and configuration.

<!-- pagebreak -->

# 2. Problem Solved

SAP IS-U consulting work often depends on narrow technical knowledge. The same issue can be analyzed repeatedly because the previous resolution is hidden in a ticket, email, spreadsheet, screenshot, local note or consultant memory. Technical evidence may be incomplete when a client asks why a defect happened, how a POD, device, installation, contract account or market-message object was affected, or whether a solution was verified.

The product addresses the following problems:

- Loss of technical knowledge when issues are solved but not converted into reusable knowledge.
- Repeated investigation of similar SAP IS-U incidents.
- Difficulty searching prior incidents by SAP object, process, affected ID or outcome.
- Lack of separation between Standard SAP knowledge and client-specific Z/private knowledge.
- Risk that an AI ancliar uses information from the wrong client context.
- Weak traceability between a technical ancliar, its sources and the evidence used.
- Manual and inconsistent knowledge-base creation.
- Fragmented documentation across SAP Help, SAP Datasheet, regulators, EDIFACT/MaKo references and consultant notes.
- Lack of structured evidence for software-assisted delivery.

The key product idea is to provide a company-developed SAP IS-U workflow around an external LLM provider. Retrieved context, namespace, source visibility, KB status, incident evidence and advisor-facing records are controlled by the application before any model output is used.

<!-- pagebreak -->

# 3. Current Implementation Status

The dossier distinguishes implemented functionality from planned or partial functionality.

## Implemented

- FastAPI local web application.
- Chat UI and backend chat sessions.
- Structured KB storage in SQLite.
- Qdrant-based vector retrieval.
- OpenAI embedding and chat integration.
- Ingesta workflow for file/text ingestion.
- KB draft review, edit, reject, approve and index controls.
- Bulk approval/indexing for current drafts.
- Standard KB and client-specific KB separation.
- Client selector and active namespace behavior.
- SAP IS-U research pipeline with topic scouting, crawling, candidate normalization, audit, promotion and indexing.
- Research/crawler output forced into Standard KB.
- Client-isolated incident database under `data/clients/<CLIENT_CODE>/incidents.sqlite`.
- Incident evidence attachments/links/notes with SHA256 for uploaded files.
- Incident-generated KB drafts.
- Annual English incident evidence PDF.
- Kanban bulk close and closed-ticket cleanup controls.
- Chat session delete and retention support.
- Backend IP Box usage logging and monthly reporting.
- Advisor documentation pack under `docs/ip_box/`.

## Partial or planned

- Full UI integration for IP usage logging is planned/TBC.
- Formal feedback UI for rating usefulness and accuracy is planned/TBC.
- Formal accuracy scoring engine is planned/TBC. The usage log supports optional `accuracy_score`, but there is no independent scoring engine yet.
- Revenue mapping and monthly IP reports require real usage records before advisor use.
- Client evidence packs require real incident records, ticket references and anonymization.

## Important factual boundary

The repository can evidence software development and current product design. It cannot, by itself, prove revenue attribution, qualifying profit or tax treatment. Those require real business records.

<!-- pagebreak -->

# 4. Innovative and Custom Elements

This section identifies the custom software elements that distinguish the tool from model-only assistance.

## Semantic SAP IS-U knowledge retrieval

The tool stores knowledge as structured KB items with title, Markdown content, type, tags, SAP objects, scope and review status. It embeds approved knowledge and searches Qdrant collections before the LLM is called. The ancliar is therefore grounded in the tool's curated knowledge, not only in the generic model.

## Standard vs. client-specific knowledge separation

The tool separates reusable Standard SAP IS-U knowledge from client-specific knowledge. This is central to confidentiality and to future IP attribution. Standard knowledge can be reused across clients. Client/Z/private knowledge belongs to the active client namespace and must not leak into another client context.

## Active namespace logic

The active client selected in the UI controls which stores and retrieval collections are available. The application can use Standard-only, client-only or client-plus-Standard retrieval, depending on the selected scope. This is proprietary application logic around security and delivery workflow.

## Governed KB review/indexing

Generated knowledge is not automatically trusted by default. Ingested or incident-generated items remain drafts until approved. The review step allows editing of content, tags and SAP objects. Approved records are then indexed for retrieval.

## Incident-to-knowledge workflow

Incidents capture problem, technical uncertainty, investigation, solution, implementation notes, verification, outcome and reusable knowledge. Useful incidents can generate KB drafts. This converts delivery work into structured internal knowledge while preserving review controls.

## Research-agent Standard KB enrichment

The research pipeline discovers SAP IS-U topics, fetches allowed sources, normalizes candidates, audits risk, promotes candidates and indexes low-risk Standard KB content. Its value is the workflow and classification layer, not copying third-party content.

## Evidence and attribution model

Usage logging, incident evidence and dossier generation create a framework for linking software-assisted work to technical output. This is relevant to advisor review, but the final IP Box position depends on actual usage records and tax analysis.

<!-- pagebreak -->

# 5. Technical Architecture

## Architecture diagram

```text
User / SAP IS-U Consultant
        |
        v
Local Browser UI
Chat | Ingesta | Incidencias | IP Box | Kanban | Finance | Settings
        |
        v
FastAPI Web Application
        |
        +--> Chat Router --------> Chat Service -------> OpenAI Chat API
        |                              |
        |                              +---------------> Qdrant Vector Search
        |                                                  |
        |                                                  +-- kb_standard
        |                                                  +-- kb_client_<code>
        |
        +--> Ingest Router ------> Extractors/Synthesis -> KB Repository
        |                                                    |
        |                                                    +-- Review/Indexing
        |
        +--> Research Router ----> Topic Scout/Crawler/Normalizer/Auditor/Ingestor/Indexer
        |                                                    |
        |                                                    +-- Standard KB only
        |
        +--> Incidents Router ---> Incident Repository ----> data/clients/<CLIENT>/incidents.sqlite
        |                                                    |
        |                                                    +-- Evidence files/links/hashes
        |                                                    +-- Annual IP Box PDF
        |
        +--> Kanban Router ------> Client Kanban Storage
        |
        +--> Finance Router -----> Finance Storage/OCR/PDF
        |
        +--> IP Box Modules -----> JSONL Usage Logs / Monthly Reports
```

## Main architecture principle

The application controls context before AI generation. The LLM receives only the context selected by the tool's retrieval, namespace and review logic. This is the core boundary between external model services and company-developed software controls.

<!-- pagebreak -->

# 6. Frontend and Desktop UI

The frontend is a local web UI designed as a consultant workbench rather than a public marketing site. It is served by FastAPI/Jinja templates with interactive behavior in the browser. The UI focuses on operational workflows:

- Select active client.
- Choose whether Standard KB is available.
- Search and ask technical SAP IS-U questions.
- Review sources and audit information.
- Ingest content.
- Review, edit, reject, approve and index KB drafts.
- Launch and monitor research-agent runs.
- Create and filter incidents.
- Add incident evidence and generate KB drafts.
- Generate annual IP Box evidence dossiers.
- Manage Kanban tickets.
- Manage finance records.
- Configure settings.

The UI is part of the company-developed software layer because it implements a domain-specific workflow for SAP IS-U consultants. It brings together namespace control, evidence capture, knowledge governance and technical retrieval in one operating surface.

## UI modules

- `src/web/templates/chat.html`: chat and source/audit panel.
- `src/web/templates/ingest.html`: ingestion, review, research and crawler workflows.
- `src/web/templates/incidents.html`: incident list, filters and create action.
- `src/web/templates/incident_detail.html`: incident editing and evidence.
- `src/web/templates/ipbox_dossier.html`: annual dossier generation.
- `src/web/templates/kanban.html`: ticket board.
- `src/web/templates/finance_*.html`: finance surfaces.
- `src/web/templates/settings.html`: configuration surface.

<!-- pagebreak -->

# 7. Business Layer and Storage Model

The backend is organized into domain modules. Each module owns its storage and behavior.

## Assistant module

The assistant module handles ingestion, storage, embedding, Qdrant indexing and chat orchestration. It defines the structured KB item model and the process for converting unstructured content into governed knowledge.

## Incidents module

The incidents module stores client-specific SAP IS-U incidents and evidence. Each client has a separate incident SQLite database. This reduces cross-client data risk and supports advisor evidence by keeping incident data traceable.

## Research module

The research module stores source registry entries, research runs, crawler runs, discovered topics and candidates. It supports Standard KB enrichment and keeps a timeline of what the agents did.

## IP Box module

The IP Box module stores and aggregates usage events. It records hashes, namespace, retrieval counts, output-used flags, estimated time saved and contribution fields. This is a backend evidence layer; full UI capture is planned/TBC.

## Kanban and finance modules

Kanban and finance support operations. They are useful product modules, but not all operational use should be treated as qualifying IP-supported delivery. Advisor review must distinguish technical SAP IS-U work from administration.

## Storage paths

- Standard/client KB: application data repositories under the configured data root.
- Incident data: `data/clients/<CLIENT_CODE>/incidents.sqlite`.
- Usage logs: `data/ip_box/usage_logs/YYYY-MM.jsonl`.
- Monthly reports: `reports/ip_box/YYYY-MM/`.
- Revenue mapping template: `reports/templates/revenue_mapping_template.csv`.

<!-- pagebreak -->

# 8. AI Manager and RAG Boundary

The AI layer uses external OpenAI services for embeddings and chat generation. The proprietary layer is the orchestration around those services.

## Retrieval flow

1. User selects active client and retrieval scope.
2. User asks a question.
3. The application creates an embedding for the question.
4. Qdrant searches the permitted Standard and/or client collections.
5. The application filters and ranks results using tags, SAP objects and score thresholds.
6. If no relevant results exist, the application can avoid calling the model to save cost and reduce hallucination risk.
7. If relevant context exists, the chat service builds a controlled prompt using retrieved sources.
8. The OpenAI chat model generates an ancliar.
9. The UI displays the ancliar and source/audit panel.

## Why this matters

The model is not the product. The product is the full controlled workflow:

- What knowledge is allowed into the index.
- How it is classified.
- Which namespace is active.
- Which documents are retrieved.
- Which sources are shown.
- Whether the model should be called.
- How the ancliar is traceable.
- How future usage can be evidenced.

## Current limitations

The application does not guarantee ancliar correctness. SAP IS-U consultants must verify ancliars against project facts, SAP systems, client policy and official documentation. Optional usefulness and accuracy fields exist in the usage log, but formal feedback UI and accuracy scoring are planned/TBC.

<!-- pagebreak -->

# 9. Knowledge Base Model

The knowledge base is structured to support retrieval, review and reuse.

## Main fields

Typical KB fields include:

- Title.
- Type, such as incident pattern, root cause, resolution, customizing note, ABAP note, glossary, runbook, SAP table, transaction, API, message or process.
- Markdown content.
- Tags.
- SAP objects.
- Scope, either Standard or client.
- Status, such as draft or approved.
- Version and timestamps.
- Source metadata where available.

## Knowledge creation paths

Knowledge can enter the system through:

- Manual text ingestion.
- PDF/DOCX ingestion.
- OpenAI-assisted synthesis.
- Incident-generated KB drafts.
- Research-agent candidates.
- Future manual curation of client-specific Z/private knowledge.

## Governance

The review process is the governance layer. Drafts can be edited, rejected or approved. Approved items are indexed in Qdrant. This reduces the risk that unreviewed model output becomes part of retrieval.

## Standard KB policy

Research/crawler output is Standard KB only. Client-specific content must be entered manually in the relevant client scope. This policy protects client confidentiality and keeps generic SAP IS-U knowledge reusable.

<!-- pagebreak -->

# 10. Standard vs. Client/Z Namespace Logic

SAP IS-U projects often include both Standard SAP objects and client-specific Z/private objects. The tool models this as a namespace and scope problem.

## Standard knowledge

Standard knowledge contains reusable SAP IS-U knowledge. Examples include general process descriptions, SAP tables, SAP transactions, SAP messages, device management concepts, FI-CA concepts, billing process notes, BPEM/EMMA patterns, IDoc/IDE/MaKo concepts and country-level market references where allowed.

## Client-specific knowledge

Client-specific knowledge includes project facts, Z objects, custom enhancements, client configuration details, client incident patterns, client screenshots, client logs and customer-specific processes. This knowledge belongs to the active client namespace.

## Active namespace

The active client selected in the UI influences:

- Which client database is used for incidents.
- Which client KB records may be retrieved.
- Which Qdrant client collection is used.
- Which evidence records are visible.
- Which draft records should be created for client-specific work.

## Leak-prevention objective

The design objective is to prevent knowledge from Client A being used in Client B ancliars. The application should prefer explicit scope selection and storage separation over relying on prompt instructions alone.

## Current and planned Z handling

The system already supports namespace separation and includes usage-log fields such as `contains_z_objects` and `namespace_applied`. Deeper automated Z-object classification, UI warnings and client-specific Z policy enforcement can be expanded in future releases.

<!-- pagebreak -->

# 11. SAP IS-U Incident Evidence Model

The Incidencias module is designed to capture a technical incident as both delivery evidence and reusable knowledge.

## Incident fields

Incident records support fields such as:

- Title.
- Client.
- Status.
- Priority.
- Year and month.
- Hours spent.
- SAP module and process.
- SAP objects.
- Affected IDs, such as POD, MaLo, device, installation, contract account, document or IDoc numbers.
- Problem statement.
- Technical uncertainty.
- Investigation.
- Solution.
- Implementation notes.
- Verification.
- Outcome.
- Reusable knowledge.
- IP Box relevance.
- Linked KB draft IDs.
- Evidence metadata.

## Evidence

Evidence can be added as file, link or note. Uploaded files receive SHA256 hashes. The evidence model supports traceability without requiring confidential content to be pasted into advisor-facing documents.

## IP Box relevance classification

The current incident classification is:

- `UNCLEAR`: needs review.
- `QUALIFYING_CANDIDATE`: may be relevant for advisor review.
- `NOT_QUALIFYING`: should normally be excluded from IP attribution.

## Dossier output

The annual incident evidence PDF is generated in English. It includes yearly totals, totals by client, totals by SAP module/process, incident table and detailed appendices for qualifying-candidate incidents. It is an evidence pack, not a tax calculation.

<!-- pagebreak -->

# 12. Research Agents and Standard KB Enrichment

The research-agent subsystem exists to enrich Standard KB with SAP IS-U reference knowledge in a controlled way.

## Agent roles

- Topic Scout: discovers or expands topic candidates from seed queries and source results.
- Source Crawler: searches configured sources and respects source usage policies where implemented.
- Collector: retrieves source material or safe internal seeds.
- Normalizer: turns source signals into structured SAP IS-U candidates.
- Auditor: assesses source, confidence, SAP relevance and copyright risk.
- Ingestor: promotes accepted candidates to KB drafts.
- Indexer: approves and indexes low-risk candidates when auto-indexing is enabled.

## Source policy

The source registry distinguishes summary-allowed, context-only and reference-only sources. This is important because the tool should not copy protected material into the KB. Where a source is reference-only, the workflow should use it only for context or exclude direct ingestion.

## Current expertise coverage

The topic catalog covers major SAP IS-U areas: master data, device management, meter reading, billing, invoicing, FI-CA, move-in/move-out, IDE/IDoc, MaKo/EDIFACT, BPEM/EMMA, transactions, customizing/SPRO, messages, ABAP/BAdIs/exits/APIs, S/4HANA Utilities/Fiori/API and selected country rules.

## What the agents own

The proprietary IP is not the public SAP fact itself. The proprietary IP is the agent workflow, source policy enforcement, topic catalog, candidate schema, audit process, KB promotion, indexing logic and user-facing monitoring.

<!-- pagebreak -->

# 13. Review, Approval and Indexing Controls

Review is the point where generated or collected content becomes governed knowledge.

## Review inside Ingesta

The Ingesta page integrates review controls so that knowledge creation and knowledge approval are not separate mental workflows. This allows a consultant to ingest, inspect, edit, approve, index or reject from one place.

## Draft status

Draft status protects the KB from unreviewed content. Drafts can come from ingestion, incidents or research agents. A draft should not affect chat retrieval until approved and indexed.

## Approved status

Approved records are suitable for indexing. Once indexed, they can be retrieved by the chat workflow within the correct namespace.

## Reject

Reject remains available even for previously approved records as an administrative cleanup and correction mechanism. Approval controls should not be shown for records that are already approved and indexed.

## Bulk approval and indexing

Bulk controls support operational efficiency when many low-risk Standard KB drafts are generated by research agents. The tool should still preserve auditability and avoid silently mixing client-specific knowledge into Standard KB.

<!-- pagebreak -->

# 14. Feedback, Accuracy and Usage Evidence

The requested product concept includes feedback and estimated accuracy. The current implementation supports part of this evidence model but does not yet implement a full feedback UI or independent accuracy engine.

## Implemented now

The backend usage log can record:

- Usage ID.
- Timestamp.
- User.
- Active client or Standard namespace.
- Ticket reference.
- Task type.
- SAP module and process.
- Search mode.
- Sources used.
- Retrieval count.
- Average similarity score.
- Whether Z/private objects were involved.
- Namespace applied.
- Output type.
- Whether output was used.
- Whether output was used for client delivery.
- Actual time.
- Estimated time without the tool.
- Estimated time saved.
- Optional usefulness rating.
- Optional accuracy score.
- Software contribution factor.
- Query and response hashes.
- Evidence path.
- Notes.

## Planned/TBC

- UI capture for every relevant chat/incident/delivery output.
- Formal consultant feedback workflow.
- Formal ancliar usefulness reporting in the UI.
- Independent accuracy estimation methodology.
- Dashboard showing precision over time.

## Advisor-useful interpretation

For IP Box evidence, the strongest metric is not a generic accuracy percentage. The stronger evidence is whether a real delivery output used the tool, which namespace was applied, which sources were retrieved, what time was saved, and whether the consultant verified the output.

<!-- pagebreak -->

# 15. Data Protection and Client Isolation

Client confidentiality is a core design constraint.

## Storage isolation

Incident data is stored per client under:

`data/clients/<CLIENT_CODE>/incidents.sqlite`

This reduces the risk of accidental cross-client incident retrieval.

## Retrieval isolation

Qdrant collections are separated between Standard KB and client-scoped KB. The active namespace determines which collections are available to a question.

## Evidence handling

Evidence records may reference confidential files or URLs. Advisor-facing reports should use hashes, titles, IDs and anonymized summaries unless disclosure is approved.

## Prompt boundary

Prompt instructions alone are not treated as sufficient security. The application controls retrieval scope before the model receives context.

## Current limitations and future controls

The backend supports namespace evidence fields. Additional UI warnings, automatic confidential-content detection and formal export anonymization can be added as roadmap controls.

<!-- pagebreak -->

# 16. AI Boundary and Third-Party IP

This section is critical for distinguishing proprietary IP from third-party tools.

## OpenAI / external model

OpenAI provides external model services used for embeddings and chat responses. The company does not own the model, model weights, OpenAI platform, or generic capabilities of the model.

## Proprietary software layer

The company-controlled software layer includes:

- Application architecture.
- UI workflows.
- Client namespace selection and filtering.
- Standard vs. client knowledge model.
- KB draft, approval and indexing workflow.
- Incident evidence data model.
- Research-agent workflow and topic catalog.
- RAG orchestration logic.
- Prompt construction and context packaging.
- Retrieval gating and source/audit presentation.
- Usage logging and monthly reporting modules.
- Annual incident evidence PDF generation.
- Tests and internal documentation.

## SAP boundary

SAP IS-U is the subject matter of the consulting work. SAP objects may be referenced as metadata, but the company does not own SAP software, SAP standard tables, transactions, programs, messages or official documentation.

## Qdrant and open-source boundary

Qdrant and open-source dependencies are infrastructure and libraries. The proprietary contribution is how the application uses them in a SAP IS-U-specific workflow.

## Client data boundary

Client data is confidential third-party data. It can evidence tool use if properly anonymized and approved, but it is not owned product IP.

<!-- pagebreak -->

# 17. IP Box Evidence Posture

SAP IS-U Assistant may be relevant to a Cyprus IP Box analysis if the software is treated as copyrighted software and if the company can show that relevant income is materially linked to the proprietary software asset.

## What this dossier supports

This dossier supports advisor review of:

- What the software product is.
- Which parts are original.
- Which parts rely on third parties.
- How the tool supports SAP IS-U technical delivery.
- How the tool separates Standard and client knowledge.
- How evidence can be captured.
- Which controls exist now.
- Which controls are planned.

## What this dossier does not support alone

This dossier does not prove:

- Final IP Box eligibility.
- Legal ownership.
- Qualifying expenditure.
- Overall expenditure.
- Nexus fraction.
- Qualifying profit.
- Transfer pricing.
- Tax savings.
- Client revenue attribution.
- That a specific invoice was software-assisted.

## Evidence required before relying on a percentage

Before any percentage of income is attributed to the tool, the company should collect:

- Real usage logs.
- Ticket references.
- Output-used confirmations.
- Incident records.
- Hours records.
- Monthly reports.
- Revenue mapping.
- Advisor-reviewed methodology.
- Management decisions.
- Anonymized examples of technical outputs.

<!-- pagebreak -->

# 18. Product Roadmap Relevant to IP Evidence

The following roadmap items would strengthen the evidence posture:

## Near term

- Integrate usage logging into Chat, Incidents and Ingesta UI flows.
- Add explicit output-used confirmation after important ancliars.
- Add feedback controls for usefulness and consultant verification.
- Add namespace warnings when client-specific/Z objects are detected.
- Add monthly advisor export from real logs.
- Add incident evidence export with anonymization controls.

## Medium term

- Add dashboard for assisted productive hours.
- Add verified-ancliar library and recurring-issue analytics.
- Add stronger source quality scoring.
- Add country-specific SAP IS-U rule packs.
- Add deeper S/4HANA Utilities/Fiori/API coverage.
- Add integration hooks for Jira, Azure DevOps or client ticket systems.

## Long term

- Package the tool as a private SaaS or controlled desktop product.
- Add multi-user authentication and role-based access.
- Add audit-ready export bundles.
- Add customer-facing licensing or managed service options if commercially appropriate.

## Evidence caveat

Roadmap items are future work. They should not be presented as implemented until the repository and usage evidence support them.

<!-- pagebreak -->

# Appendix A. Module Inventory

## Web application

- `src/web/app.py`: FastAPI application wiring.
- `src/web/routers/chat.py`: chat session and RAG API surface.
- `src/web/routers/ingest.py`: ingestion and review API surface.
- `src/web/routers/research.py`: research/crawler API surface.
- `src/web/routers/incidents.py`: incident and dossier API surface.
- `src/web/routers/kanban.py`: Kanban API surface.
- `src/web/routers/finance.py`: finance API surface.
- `src/web/routers/settings.py`: settings API surface.

## Assistant

- `src/assistant/chat/chat_service.py`: ancliar orchestration.
- `src/assistant/retrieval/embedding_service.py`: embeddings.
- `src/assistant/retrieval/qdrant_service.py`: vector search and collections.
- `src/assistant/retrieval/kb_indexer.py`: indexing.
- `src/assistant/storage/kb_repository.py`: KB persistence.
- `src/assistant/ingestion/synthesis.py`: structured synthesis.
- `src/assistant/ingestion/extractors.py`: file/text extraction.

## Incidents and IP evidence

- `src/incidents/storage/incident_repository.py`: incident/evidence persistence.
- `src/incidents/pdf/ipbox_dossier.py`: annual incident evidence PDF.
- `src/ipbox/usage_logging.py`: backend usage logging.
- `src/ipbox/reporting.py`: monthly usage reports and CSV export.

## Research

- `src/research/agents/topic_catalog.py`: curated SAP IS-U topic catalog.
- `src/research/agents/crawler.py`: autonomous crawler.
- `src/research/agents/workflow.py`: research pipeline logic.
- `src/research/agents/orchestrator.py`: run orchestration.
- `src/research/storage/research_repository.py`: research persistence.

<!-- pagebreak -->

# Appendix B. Evidence Checklist

The following checklist should be maintained with real records:

- Repository URL and commit history.
- Release tags and changelog reconciliation.
- Screenshots of implemented UI screens.
- Test results.
- Incident examples, anonymized where needed.
- KB item exports.
- Qdrant collection configuration evidence.
- Research-agent run logs.
- Usage logs by month.
- Monthly usage reports.
- Ticket references linked to usage IDs.
- Revenue mapping to invoices.
- Management decisions and roadmap approvals.
- Third-party license review.
- Advisor review notes.

## Evidence quality rules

- Do not backdate records.
- Do not invent logs or usage.
- Do not include client confidential content without approval.
- Mark planned work as planned.
- Preserve source references for public knowledge.
- Keep Standard and client-specific knowledge separate.

<!-- pagebreak -->

# Appendix C. Current Limitations

The current product is useful, but the following limitations matter for advisor review:

- Full UI-driven usage logging is not yet integrated.
- Formal feedback and accuracy UI is not implemented.
- Real usage logs are required before any income attribution model is reliable.
- Research-agent coverage is useful but not exhaustive SAP IS-U expertise.
- Public source availability can be affected by robots.txt, timeouts, SSL issues and source policies.
- SAP official documentation and licensed content cannot be copied into the KB.
- Client-specific knowledge must be manually controlled.
- Finance and generic administrative use should normally be excluded from technical IP attribution.
- Final tax treatment requires qualified Cyprus advisor review.

<!-- pagebreak -->

# Appendix E. Attribution Safeguards

## Maximum position

Any position up to 100% is exceptional and aggressive. It should not be treated as a current claim. It requires near-total workflow centrality, complete monthly usage logs, ticket-level evidence, output-used confirmation, human review, invoice/timesheet reconciliation and explicit advisor approval.

## 60% target scenario

The 60% position is a target scenario, not an achieved result. It is supported only when real logs produce the formula inputs:

- assisted productive SAP IS-U hours;
- total productive SAP IS-U hours;
- software contribution factor;
- qualifying service factor;
- client-delivery output evidence;
- human review/verification;
- revenue mapping.

## Model-only boundary

Work should not be attributed to the software asset merely because an external AI model was used. The evidence should show that SAP IS-U Assistant's company-developed layer materially contributed through retrieval, namespace filtering, KB/incident workflows, source audit, usage logging or dossier/report generation.

<!-- pagebreak -->

# Appendix D. Advisor Questions

The company should ask advisors to review:

- Whether SAP IS-U Assistant qualifies as copyrighted software under the relevant Cyprus rules.
- Whether the legal owner and developer records support the claimed ownership.
- Which development costs may be qualifying expenditure.
- How to treat OpenAI, Qdrant and other third-party dependencies.
- Whether software-assisted consulting income can be included and under what methodology.
- What percentage methodology is acceptable.
- What logs and ticket-level evidence are required.
- How to anonymize client confidential data.
- Whether future SaaS/licensing models would strengthen the position.
- How to document nexus-style traceability.

## Closing statement

SAP IS-U Assistant should be presented as a company-developed software product that uses third-party AI as a provider, not as a claim to own SAP knowledge or the OpenAI model. The strongest evidence position will come from consistent use of the tool in real SAP IS-U delivery, reliable usage logs, client-isolated incident records, governed knowledge management and advisor-reviewed revenue mapping.
