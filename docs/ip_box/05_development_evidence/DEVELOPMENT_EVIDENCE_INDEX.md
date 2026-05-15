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
| Test run logs | `docs/ip_box/evidence/test_runs/` | Folder prepared | Add real command output files only. |
| Release notes | `docs/ip_box/evidence/release_notes/` | Folder prepared | Add real release notes only. |
| Anonymized cases | `docs/ip_box/evidence/anonymized_cases/` | Folder prepared | Remove client secrets and production data. |
| Incident evidence | `data/clients/<CLIENT>/incidents.sqlite` | Available when populated | Do not include confidential data in advisor pack without review. |
| Usage logs | `data/ip_box/usage_logs/` | Workflow implemented | Requires real usage entries and monthly review. |
| Usage evidence review | `/ipbox/usage` | Implemented | Reviews actual recorded events; does not invent entries. |
| Monthly reports | `reports/ip_box/YYYY-MM/` | Implemented | Generated from real usage entries; not a tax calculation. |

## Required Manual Actions

1. Export real commit history.
2. Capture screenshots of key workflows.
3. Save test output logs for each release.
4. Link real incidents and anonymised ticket references.
5. Review monthly usage events and complete missing references.
6. Keep advisor-reviewed evidence separate from raw confidential data.
