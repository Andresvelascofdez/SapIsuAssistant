# Technical Decisions

| Decision | Rationale | Evidence | Status |
| --- | --- | --- | --- |
| Use local FastAPI desktop-style app | Fast internal workflow without external SaaS exposure | `src/web/app.py` | Implemented |
| Use SQLite for operational records | Simple local persistence and client isolation | storage repositories | Implemented |
| Use Qdrant for semantic retrieval | Better SAP IS-U similarity search than keyword-only search | `src/assistant/retrieval/qdrant_service.py` | Implemented |
| Separate Standard and client knowledge | Confidentiality and no cross-client leakage | `ClientManager`, Qdrant scopes | Implemented |
| Keep KB items as drafts before approval | Avoid unreviewed knowledge entering chat retrieval | review router and Ingesta UI | Implemented |
| Build incident evidence module | Link technical incidents to reusable knowledge and IP Box evidence | `src/incidents/` | Implemented |
| Build research agents for Standard KB | Populate standard SAP IS-U knowledge with audit trail | `src/research/` | Implemented |
| Add usage logging as separate module | Evidence without destabilizing main app flows | `src/ipbox/` | Implemented |
| UI logging integration | Needed for routine use capture | TBC | Planned |
