# Knowledge Base Provenance

## Knowledge Types

- Standard SAP IS-U knowledge: reusable technical knowledge stored in Standard KB.
- Research-agent knowledge: candidates generated from permitted public sources or safe internal seeds, reviewed and indexed.
- Manually created knowledge: user-entered notes and documentation.
- Incident knowledge: anonymised or client-scoped incident patterns and resolutions.
- Client-specific Z knowledge: private client knowledge that must stay in that client namespace.

## Current Controls

- Standard and client scopes are stored separately.
- Qdrant collections are separated for Standard and clients.
- KB drafts require approval before retrieval.
- Research agents force Standard KB.
- Incident-derived KB drafts are client-scoped.

## Excluded Sources

- SAP proprietary documentation copied verbatim beyond permitted short summaries.
- SAP PRESS/Rheinwerk book content.
- Client confidential data in Standard KB.
- Unverified public content without review.

## Provenance Table Template

| Entry ID | Category | Source Type | Source Description | Owner | Usage Permission | Client Namespace | Standard/Z | Verification Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KB-EXAMPLE | SAP_TABLE | Public technical dictionary | SAP Datasheet summary | Third party | Summary/reference only | STANDARD | Standard | Reviewed | Example only |
