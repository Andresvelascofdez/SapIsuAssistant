# Data Protection and Confidentiality Controls

## Implemented Controls

- Local storage by default.
- Client directories under `data/clients/<CLIENT_CODE>/`.
- Client-specific incident SQLite databases.
- Standard and client KB separation.
- Qdrant collection separation by scope.
- Evidence file hashing.
- API key stored via environment/`.env`/Settings rather than hardcoded source.
- Usage logs store query/response hashes rather than full text by default.

## Required Operating Controls

- Do not place client confidential content in Standard KB.
- Use anonymised placeholders in advisor packs.
- Review any exported evidence before sharing.
- Avoid sending unnecessary confidential text to external APIs.
- Maintain deletion/export procedures per client.

## Planned/TBC

- Formal UI warnings for confidential usage logging.
- Advisor export redaction workflow.
- Client data retention policy.
- Automated cross-client leakage test pack.
