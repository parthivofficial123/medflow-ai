# Handoff

_Last updated: 2026-10-20, end of Day 1 (vertical slice)._

## Goal
Build the MedFlow AI MVP in 8 days, following `docs/PLAN.md`. Day 1 slice is done and **waiting for review. Do not start Day 2 until it's approved.**

## Current state
- Day 1 slice works: appointments list + add form → `storage.py` → `instance/appointments.json`.
- `pytest`: 35 passed. Acceptance criteria S1–S6 pass.
- Checked in the browser at 375px (light) and 1024px (dark): no horizontal scroll, invalid submit shows errors and keeps input, valid submit saves and sorts. Not re-checked at 1280px after the last CSS fix (the browser pane was closed).
- Git repo on `main`; first commit holds the docs and the Day 1 slice. `instance/` and `.venv/` are gitignored (verified with `git check-ignore`).
- Venv: Python 3.14.5, Flask 3.1.3, pytest 8.4.2.
- Project lives in `Desktop\BettermindLabs_MedFlow`.

## Active files
- `medflow/__init__.py`: app factory, CSRF check, date/time filters, 400/404 pages, `reset-demo`
- `medflow/storage.py`: load / save (atomic) / next_id / seed_missing / reset
- `medflow/appointments.py`: blueprint, `validate()`, list + create
- `medflow/templates/`: `base.html`, `_macros.html` (`field` macro), `appointments/list.html`, `error.html`
- `medflow/static/css/app.css`: design tokens (light + dark), components
- `data/seed/appointments.json`: 4 fictional appointments
- `tests/`: `conftest.py`, `test_storage.py`, `test_appointments.py`

## Decisions made
- CSRF: per-session token (`secrets.token_urlsafe`), constant-time compare, accepted from the form field or the `X-CSRFToken` header. No Flask-WTF.
- Forms use `novalidate`. The server is the single source of validation messages so they look the same everywhere; `required`/`maxlength` stay for accessibility.
- No `app.js` yet: nothing on Day 1 needs JavaScript.
- Concurrency: atomic writes only, last-write-wins (documented in `storage.py` and `CLAUDE.md`).
- A corrupt data file currently surfaces as a 500 with a message saying to run `reset-demo`.

## Failed attempts / dead ends
- Mobile overflow: a single-column grid grew to the date/time inputs' intrinsic width. Fixed with `minmax(0, 1fr)` tracks and `min-width: 0` on inputs. Use the same pattern for future grids.

## Next steps (after approval)
1. Review Day 1 in the browser (including 1280px).
2. Day 2 per `docs/PLAN.md`: edit/delete, status, follow-up tasks, reminder field, upcoming/past split (A1–A5).
3. Reuse `validate()` for edit; add a small `app.js` only for the delete confirmation.
