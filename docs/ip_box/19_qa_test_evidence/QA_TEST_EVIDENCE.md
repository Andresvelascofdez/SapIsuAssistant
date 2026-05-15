# QA Test Evidence

## Test Categories

- Namespace filtering.
- Standard vs. Z separation.
- Client active filtering.
- Standard mode excluding Z/private knowledge.
- Combined search.
- Incident-only search.
- AI-only search.
- Feedback logging.
- Accuracy scoring.
- Usage logging.
- Monthly report generation.
- Revenue mapping export.

## Specific Test Cases

### Test 1: Standard Scope Excludes Client Z Data

- Active client: STANDARD.
- Query includes Z object from CLIENT_A.
- Expected: no CLIENT_A Z data returned.
- Status: Covered at collection-routing level by `tests/test_v020_features.py`; real UI screenshot evidence still TBC.

### Test 2: Client A Includes Permitted Client Knowledge

- Active client: CLIENT_A.
- Query includes CLIENT_A Z object.
- Expected: Standard knowledge plus CLIENT_A knowledge returned.
- Status: Covered at retrieval-routing level by `tests/test_v020_features.py`; real delivery example still TBC.

### Test 3: No Cross-Client Incident Leakage

- Active client: CLIENT_B.
- Query similar to CLIENT_A incident.
- Expected: CLIENT_A incident not returned.
- Status: Incident storage/API isolation covered by `tests/test_incidents.py`; chat-level incident retrieval evidence remains TBC if that workflow is expanded.

### Test 4: Combined Mode

- Expected: technical answer plus permitted similar incidents.
- Status: Requires dedicated test evidence.

### Test 5: Usage Logging

- Expected: usage_id generated and mandatory fields saved.
- Status: Covered by `tests/test_ipbox_usage_reporting.py`.

### Test 6: Usage Evidence Review UI

- Expected: actual usage events can be listed, reviewed, updated and exported into a monthly report.
- Status: Covered by `tests/test_ipbox_usage_reporting.py`.

### Test 7: Research-Agent Standard KB Policy

- Expected: automatic research/crawler output is written to Standard KB, not client namespaces.
- Status: Covered by `tests/test_research_pipeline.py`.

### Observed Local Test Runs

These are local command results from 2026-05-15 and should be supplemented with saved CI/test-run artefacts before advisor submission:

- `pytest -q tests/test_ipbox_usage_reporting.py tests/test_incidents.py tests/test_research_pipeline.py tests/test_ui_controls.py --maxfail=1`: 47 passed.
- `pytest -q tests/test_comprehensive.py tests/test_v020_features.py --maxfail=1`: 323 passed.
- `pytest -q tests/test_env_and_synthesis_schema.py tests/test_kanban_bulk.py tests/test_comprehensive.py tests/test_v020_features.py tests/test_ipbox_usage_reporting.py tests/test_incidents.py tests/test_research_pipeline.py tests/test_ui_controls.py --maxfail=1`: 376 passed.
- `pytest -q --maxfail=1`: timed out after 10 minutes in this local session.
- `pytest -q tests/test_finance.py --maxfail=1`: timed out after 5 minutes in this local session; Finance/OCR-heavy evidence should be run separately before release sign-off.
