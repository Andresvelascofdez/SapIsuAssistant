# Internal User Guide

## Starting the App

Run `python run.py` and open `http://localhost:8000`.

## Selecting Client

Use the client selector in the header. Use Standard KB for reusable SAP IS-U knowledge and client scope only for permitted client-specific content.

## Registering Incidents

Open Incidencias, create an incident, classify SAP module/process, add SAP objects, affected IDs, narrative fields and evidence. Mark IP Box relevance only as a preliminary internal classification.

## Technical Search

Use Chat for RAG-based technical search. Select Standard, client or client plus standard scope as appropriate.

## Ingesta and Review

Use Ingesta to add knowledge and review KB drafts. Drafts must be approved before chat retrieval.

## Research Agents

Use the SAP IS-U Research area in Ingesta to run topic research, crawler or catalog runs. Research output goes to Standard KB.

## Usage Logging

Backend usage logging is available through `src/ipbox/usage_logging.py`. UI integration is planned. Until then, usage events can be created by scripts or future API/UI wrappers.

## Monthly IP Report

Use `src/ipbox/reporting.py` to generate monthly reports from usage logs.

## Advisor Pack

Use `docs/ip_box/25_advisor_pack/ADVISOR_PACK_INDEX.md` as the checklist before sending material to advisors.
