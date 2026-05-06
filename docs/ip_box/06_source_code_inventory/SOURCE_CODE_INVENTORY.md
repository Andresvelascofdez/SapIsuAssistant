# Source Code Inventory

| Module | File | Function | Proprietary IP Contribution | Criticality | Evidence Available | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Web App | `src/web/app.py` | FastAPI application and router wiring | Application shell | High | Source/tests | Implemented |
| Chat | `src/web/routers/chat.py` | Chat API and session handling | RAG workflow surface | High | Source/tests | Implemented |
| Chat | `src/assistant/chat/chat_service.py` | Ancliar generation | AI orchestration | High | Source/tests | Implemented |
| Retrieval | `src/assistant/retrieval/qdrant_service.py` | Qdrant collections/search | Namespace retrieval control | High | Source/tests | Implemented |
| Retrieval | `src/assistant/retrieval/embedding_service.py` | Embedding generation | AI search integration | High | Source/tests | Uses OpenAI |
| KB Storage | `src/assistant/storage/kb_repository.py` | KB item persistence | Dedupe/versioning model | High | Source/tests | Implemented |
| Ingestion | `src/assistant/ingestion/synthesis.py` | Structured synthesis | Prompt/workflow logic | High | Source/tests | Implemented |
| Review | `src/web/routers/review.py` | Approval/rejection/indexing | Knowledge governance | High | Source/tests | Implemented |
| Incidents | `src/incidents/storage/incident_repository.py` | Incident and evidence storage | IP evidence data model | High | Source/tests | Implemented |
| Incidents | `src/web/routers/incidents.py` | Incident APIs and KB drafts | Delivery evidence workflow | High | Source/tests | Implemented |
| IP Dossier | `src/incidents/pdf/ipbox_dossier.py` | Annual evidence PDF | Advisor evidence output | Medium | Source/tests | No tax calculation |
| Research | `src/research/agents/crawler.py` | Autonomous source crawler | Standard KB enrichment workflow | High | Source/tests | Implemented |
| Research | `src/research/agents/orchestrator.py` | Agent orchestration | Multi-step knowledge pipeline | High | Source/tests | Implemented |
| Research | `src/research/agents/topic_catalog.py` | SAP IS-U topic catalog | Curated expertise structure | High | Source/tests | Implemented |
| Research | `src/research/storage/research_repository.py` | Research state persistence | Audit trail for agents | High | Source/tests | Implemented |
| IP Evidence | `src/ipbox/usage_logging.py` | Usage logging | Attribution evidence | High | Source/tests | Backend module |
| IP Evidence | `src/ipbox/reporting.py` | Monthly reports and revenue template | Attribution reporting | High | Source/tests | Backend module |
| Kanban | `src/kanban/storage/kanban_repository.py` | Ticket board | Operational support | Medium | Source/tests | Not automatically qualifying |
| Finance | `src/finance/storage/finance_repository.py` | Finance records | Admin support | Low | Source/tests | Generally excluded |
