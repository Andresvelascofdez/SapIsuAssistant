# Engineering Procedures & Best Practices (Error-Minimizing Rules for Codex)

This document is a **hard rulebook**. Codex must follow it strictly.

---

## 1) Absolute Rules (Non-Negotiable)

1. **Do not create unnecessary files.**
   - Only create files explicitly required by the plan.
   - Do not create “scratch”, “notes”, “tmp”, “backup”, “v2”, “final”, or similar files.

2. **No test artifacts left behind.**
   - All tests must use `pytest` and `tmp_path`.
   - Any files/DBs created for tests must exist only under `tmp_path` and must not persist.
   - Never write tests that touch `./data/` or real client folders.

3. **Do not break working code.**
   - If something works, do not refactor it.
   - Bugfix process is always: (a) reproduce via test, (b) minimal fix, (c) all tests pass.

4. **No duplicate implementations.**
   - Never implement the same logic in multiple places.
   - Prefer single source of truth functions/services.

5. **No icons/emojis** in UI or code strings.

6. **Minimal comments**, English only.
   - Prefer clear naming and small functions.
   - Comments must explain “why”, not “what”.

7. **Test gate before moving forward.**
   - After every key feature, run `pytest`.
   - If failing, fix immediately before adding new features.

8. **Frequent Git commits + pushes.**
   - Commit and push at the end of every milestone and meaningful sub-step.

---

## 2) Required Development Workflow (Codex Procedure)

For each milestone:

1. **Read the milestone spec** and list deliverables.
2. **Implement smallest viable slice** that satisfies deliverables.
3. **Add/Update tests** for the slice.
4. **Run `pytest`** until green.
5. **Remove debug code** (print statements, temporary logs).
6. **Check repo hygiene** (no new unintended files).
7. **Commit and push** with a clear message.

Commit message format:
- `feat: ...`
- `fix: ...`
- `test: ...`
- `chore: ...`

---

## 3) File Hygiene Rules

### 3.1 Allowed file creation
Only these types are allowed:
- Source code under `src/`
- Tests under `tests/`
- CI configs under `.github/`
- `README.md`, `pyproject.toml`, `.gitignore`, `docker-compose.yml`

### 3.2 Forbidden file patterns
Must never appear:
- `*_v2.*`, `*_final.*`, `temp.*`, `tmp.*`, `debug.*`, `notes.*`
- random `scripts/` created without explicit plan requirement
- generated data under version control

### 3.3 Data folder policy
- `./data/` must be gitignored.
- No real or sample customer data in git.
- Only synthetic example JSON may appear under `tests/fixtures/` if truly needed.

---

## 4) Testing Rules (Strict)

### 4.1 Unit tests
- Must cover:
  - client isolation logic (paths/DB opening)
  - KB item dedupe/versioning
  - ingestion status transitions
  - retrieval query scoping (only standard + active client)
  - Kanban separation (never touches assistant DB)

### 4.2 Integration tests (Optional and controlled)
- Qdrant integration tests run only when:
  - environment variable `RUN_QDRANT_IT=1`
- They must:
  - start from empty collections (or unique test collections)
  - delete any test collections at end
  - never touch real collections

### 4.3 Test artifacts must be ephemeral
- Use `tmp_path` for:
  - sqlite DBs
  - docx/pdf sample generation
  - any file-based fixtures
- Never write to working directory during tests.

---

## 5) Bugfix Policy (“Never break what works”)

When a bug is reported:
1. Write a failing test reproducing the bug.
2. Identify the **smallest** change to fix it.
3. Apply fix.
4. Ensure:
   - the new test passes
   - all existing tests pass
5. Do not refactor unrelated code.

---

## 6) Qdrant Rules

1. Collections must be created only if missing.
2. Collection naming is fixed:
   - `kb_standard`
   - `kb_<CLIENT_CODE>`
3. Search must never query other client collections.
4. Payload must stay minimal (no full content).
5. If embedding model/dimension changes:
   - create new collections and reindex (no silent dimension mismatch).

---

## 7) OpenAI API Rules

1. API key via environment variable only.
2. Never print or log secrets.
3. Synthesis pipeline:
   - uses `gpt-5.2` with `reasoning.effort=xhigh`
   - must return schema-valid JSON
4. If schema invalid:
   - perform exactly one controlled retry
   - then mark ingestion `FAILED`

---

## 8) Logging & Error Handling Rules

- Logging should be minimal and non-sensitive.
- User-visible errors must be clear and actionable:
  - Qdrant down: “Qdrant is not reachable. Start docker-compose and retry.”
  - OpenAI error: show request id (if available) and short message
- Never dump full prompts or user content into logs by default.

---

## 9) UI Quality Rules

- Keep UI simple and consistent.
- No icons/emojis.
- Avoid complex drag-and-drop if it risks instability; prefer reliable controls first.
- Any UI feature must be backed by stable storage logic first.

---

## 10) Git & Branching

- Default branch: `main`
- Work in short-lived branches only if necessary.
- Push after each milestone:
  - CI must pass on GitHub Actions.

---

## 11) Final “No Surprise” Checklist (Run Before Every Push)

- `pytest` green
- no new unexpected files
- `.gitignore` still excludes `data/`
- no secrets in repo
- no test artifacts outside `tmp_path`
- Qdrant collection names unchanged
- client isolation guarantees still enforced by tests
