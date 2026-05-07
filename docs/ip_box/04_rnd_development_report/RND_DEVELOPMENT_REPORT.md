# Software R&D / Technical Development Report

This document describes software development challenges. It does not claim scientific research. It records technical uncertainty and engineering work relevant to the proprietary software asset.

## Challenge 1: Reusable SAP IS-U Technical Knowledge

- Problem: SAP IS-U knowledge is fragmented across incidents, SAP objects, public references and consultant memory.
- Technical uncertainty: how to structure reusable knowledge without mixing client confidential content.
- Solution: KB item model with types, tags, SAP objects, signals, sources and Standard/client scopes.
- Evidence: `src/assistant/storage/kb_repository.py`, `src/research/`, tests in `tests/test_research_pipeline.py`.
- Business value: faster reuse of technical analysis and repeatable client delivery.

## Challenge 2: Standard vs. Client-Specific Knowledge Separation

- Problem: SAP standard knowledge and client Z/private knowledge must not leak across clients.
- Technical uncertainty: how to maintain retrieval isolation while allowing Standard plus client mode.
- Solution: client-scoped SQLite DBs and Qdrant collections.
- Evidence: `src/shared/client_manager.py`, `src/assistant/retrieval/qdrant_service.py`.
- Business value: supports confidentiality and internal control.

## Challenge 3: AI + Knowledge Base + Incident Retrieval Workflow

- Problem: external model ancliars without application-controlled SAP IS-U context are not enough for SAP IS-U consulting.
- Technical uncertainty: how to combine curated KB, incident evidence and AI-generated output.
- Solution: RAG chat, KB review, incident KB draft generation and source audit panel.
- Evidence: `src/assistant/chat/chat_service.py`, `src/web/routers/chat.py`, `src/web/routers/incidents.py`.
- Business value: more consistent technical responses.

## Challenge 4: Traceability of AI-Assisted Work

- Problem: IP Box support requires evidence that the tool materially assisted work.
- Technical uncertainty: which fields are sufficient without storing excessive confidential text.
- Solution: usage log records hashes, ticket references, time estimates, output-used status and contribution factor.
- Evidence: `src/ipbox/usage_logging.py`, `src/ipbox/reporting.py`.
- Business value: enables monthly attribution reports.

## Challenge 5: Accuracy Estimation and Feedback

- Problem: AI output must be reviewed and validated.
- Technical uncertainty: how to record usefulness and accuracy without overclaiming.
- Current status: usage logs include optional `usefulness_rating` and `accuracy_score`; a full feedback UI is planned/TBC.
- Evidence: `src/ipbox/usage_logging.py`.
- Business value: supports advisor review and quality improvement once real data is collected.

## Challenge 6: Vector Search Architecture

- Problem: keyword search is insufficient for technical SAP IS-U reuse.
- Technical uncertainty: how to retrieve semantically similar knowledge while respecting scope.
- Solution: OpenAI embeddings and Qdrant collections per scope.
- Evidence: `src/assistant/retrieval/embedding_service.py`, `src/assistant/retrieval/qdrant_service.py`.
- Business value: faster retrieval of relevant knowledge and incident patterns.
