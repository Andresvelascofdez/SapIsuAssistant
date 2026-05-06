# Development Evidence Index

This index must be completed from actual evidence only. Do not invent commit hashes, screenshots, dates, hours or logs.

| Evidence Type | Location | Current Status | Notes |
| --- | --- | --- | --- |
| Source code | Repository root | Available | Confirm ownership and authorship. |
| Git commits | GitHub repository | To be extracted | Add real commit hashes only. |
| Version tags | GitHub repository | To be confirmed | Create tags only for actual releases. |
| Tests | `tests/` | Available | Include test run logs. |
| README | `README.md` | Available | Product overview. |
| Changelog | `CHANGELOG.md` | Available | Functional release history. |
| Screenshots | `docs/ip_box/evidence/screenshots/` | To be collected | Use real screenshots with dates. |
| Incident evidence | `data/clients/<CLIENT>/incidents.sqlite` | Available when populated | Do not include confidential data in advisor pack without review. |
| Usage logs | `data/ip_box/usage_logs/` | Module implemented | Requires real usage entries. |
| Monthly reports | `reports/ip_box/YYYY-MM/` | Module implemented | Requires real usage entries. |

## Required Manual Actions

1. Export real commit history.
2. Capture screenshots of key workflows.
3. Save test output logs for each release.
4. Link real incidents and anonymised ticket references.
5. Keep advisor-reviewed evidence separate from raw confidential data.
