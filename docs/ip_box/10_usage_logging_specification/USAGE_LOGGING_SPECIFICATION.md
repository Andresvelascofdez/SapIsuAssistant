# Usage Logging Specification

## Implementation Status

Backend logging is implemented in `src/ipbox/usage_logging.py`. Monthly aggregation is implemented in `src/ipbox/reporting.py`. UI capture is planned/TBC.

## Storage

Usage events are saved as JSONL under:

`data/ip_box/usage_logs/YYYY-MM.jsonl`

Reports are generated under:

`reports/ip_box/YYYY-MM/`

## Fields

| Field | Purpose |
| --- | --- |
| usage_id | Unique usage identifier |
| timestamp | UTC timestamp |
| user | Internal user |
| active_client | Active client or STANDARD |
| ticket_reference | Ticket/task reference |
| invoice_reference | Optional invoice reference |
| task_type | Incident, Jira response, debug checklist, documentation, etc. |
| sap_module | SAP module |
| sap_isu_process | IS-U process |
| search_mode | AI_ONLY / INCIDENTS_ONLY / COMBINED |
| sources_used | KNOWLEDGE_BASE / INCIDENTS / BOTH / MANUAL_CONTEXT |
| number_of_documents_retrieved | Retrieval count |
| average_similarity_score | Average similarity, if available |
| contains_z_objects | Whether Z/private objects were involved |
| namespace_applied | STANDARD or client namespace |
| output_type | TECHNICAL_ANALYSIS / JIRA_RESPONSE / EMAIL / DEBUG_CHECKLIST / DOCUMENTATION / TRANSLATION / OTHER |
| output_used | YES / PARTIAL / NO |
| used_for_client_delivery | YES / NO |
| human_reviewed | Whether a consultant reviewed the generated output before use |
| verification_status | Review status such as NOT_RECORDED, CONSULTANT_VERIFIED, NEEDS_CORRECTION, REJECTED |
| software_features_used | Semicolon-separated features used, such as CHAT_RAG, KB_RETRIEVAL, INCIDENT_SEARCH, KB_DRAFT, DOSSIER |
| retrieved_kb_item_ids | KB item IDs used for traceability |
| retrieved_incident_ids | Incident IDs used for traceability |
| output_reference | Jira/comment/email/document reference where the output was used |
| actual_time_minutes | Actual time spent |
| estimated_time_without_tool_minutes | Estimated manual time |
| estimated_time_saved_minutes | Estimated time saved |
| usefulness_rating | Optional 1-5 rating |
| accuracy_score | Optional 0-1 score |
| software_contribution_factor | Management estimate 0-1 |
| query_hash | SHA256 hash |
| response_hash | SHA256 hash |
| evidence_path | Link/path to evidence |
| notes | Free notes |

## Confidentiality

The logger stores hashes by default for query/response text. Full confidential content should not be stored in advisor packs unless reviewed and anonymised.

## Sufficiency for Monthly Reports

The field set is designed to support monthly evidence reports by linking usage to client, ticket, SAP process, retrieval scope, source type, software features used, output-use confirmation, human review, time records and revenue mapping. A monthly percentage should not be relied upon unless the usage log reconciles with timesheets, invoices and ticket-level evidence.
