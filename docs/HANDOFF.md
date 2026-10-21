# Handoff

_Last updated: 2026-10-20. **Day 2 + audit remediation complete. Waiting for approval before Day 3.**_

## Goal
Build the MedFlow AI MVP in 8 days, following `docs/PLAN.md`. Next: Day 3 (expenses, E1–E5), only after approval.

## Current state
- Days 1–2 done; the audit fixes ("Day 2.5") are committed locally. Nothing is pushed.
- `pytest`: 110/110 pass.
- Concurrency verified two ways: the pytest tests (20 concurrent task adds; 10 writes + 10 reads at once) fail with the lock disabled and pass with it, and a repeat probe against a real threaded `flask run` server (20 parallel POSTs) gave 20/20 HTTP 302 and 20/20 tasks saved with unique ids.

## Audit fixes (Day 2.5)
1. **Lost updates / Windows `PermissionError`.** New `storage.modify(name)` context manager: load → change → save under one re-entrant lock; `load` takes the same lock so a reader never holds the file open during `os.replace`. Every appointment write route uses it, and validation happens before the lock. An exception or `abort` inside it saves nothing.
2. **Non-canonical dates/times.** `appointments.validate()` stores `YYYY-MM-DD` / `HH:MM` (`2026-1-5` → `2026-01-05`, `9:5` → `09:05`). Malformed values (`2026/01/05`, `2026-02-30`, `12:60`, `24:00`, `09:05:00`, …) are rejected.
3. **Error pages.** Friendly 405 and 500 pages. The 500 page suggests `reset-demo` only for a `StorageError` (corrupt JSON), and never shows exceptions, tracebacks or paths. `reset-demo` now asks for confirmation and warns that it replaces all changes (`--yes` skips the prompt).
4. **Specs finalized in `docs/PLAN.md`:** the expense data model and summary definitions (Decimal, cents, null ≠ 0, paid amounts, estimates never "owed"), the price comparison data model and comparability rules, and the feature integration rules, including the multi-file write limitation.

## Active files
- `medflow/storage.py`: `load`, `save`, `modify`, `next_id`, `seed_missing`, `reset`, `StorageError(collection, detail)`
- `medflow/__init__.py`: error handlers (400/404/405/500), `reset-demo` confirmation
- `medflow/appointments.py`: `find()` replaces `load_one()`; writes via `storage.modify`
- `tests/test_storage.py`, `tests/test_appointments.py`
- `docs/PLAN.md` (expense, price and integration specs), `CLAUDE.md` (storage, money and debug rules)

## Known limitations
- The lock is per process: correct for `flask run`, not for several server processes.
- Changes spanning two JSON files are two atomic writes, not a transaction; the write order in PLAN.md keeps the worst case harmless.
- With `--debug`, Flask shows its debugger instead of the friendly 500 page (by design; debug is local only).
- `SECRET_KEY` falls back to a fixed dev value. Must be set via `MEDFLOW_SECRET_KEY` before any non-local use.
- Seed dates are fixed: after 2026-10-23 no reminder is due in the demo until one is edited.
- Your `instance/` still holds the pre-Day-2 data. Run `flask --app medflow reset-demo` (it asks first) to see the Day 2 demo data.
- A past appointment can stay "scheduled"; the Day 5 dashboard should flag it.

## Failed attempts / dead ends
- Mobile overflow from date/time inputs: use `minmax(0, 1fr)` and `min-width: 0`.
- Utility-class specificity: `.page-header .page-header__jump` beats the later `.btn`.
- Locking `load` and `save` separately does not stop lost updates; the whole read-modify-write must hold the lock (`storage.modify`).

## Next steps: Day 3 (after approval)
Follow "Expense specification (Day 3)" and "Feature integration rules" in `docs/PLAN.md`:
1. `medflow/expenses.py` + `data/seed/expenses.json` (fictional); Decimal money parser with tests first (`0.29`, `19.99`, `$1,234.56`, `NaN`, negatives, 3 decimals).
2. CRUD with `storage.modify`; derived status; summary function with hand-computed test totals.
3. Link to appointments; list linked expenses on the appointment page; on appointment delete, unlink expenses first and update the confirmation text.
4. Nav link; checks at 375px and 1280px; `/code-review`; commit.
