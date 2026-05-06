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
- Status: Requires dedicated test evidence.

### Test 2: Client A Includes Permitted Client Knowledge

- Active client: CLIENT_A.
- Query includes CLIENT_A Z object.
- Expected: Standard knowledge plus CLIENT_A knowledge returned.
- Status: Requires dedicated test evidence.

### Test 3: No Cross-Client Incident Leakage

- Active client: CLIENT_B.
- Query similar to CLIENT_A incident.
- Expected: CLIENT_A incident not returned.
- Status: Requires dedicated test evidence.

### Test 4: Combined Mode

- Expected: technical ancliar plus permitted similar incidents.
- Status: Requires dedicated test evidence.

### Test 5: Usage Logging

- Expected: usage_id generated and mandatory fields saved.
- Status: Covered by `tests/test_ipbox_usage_reporting.py`.
