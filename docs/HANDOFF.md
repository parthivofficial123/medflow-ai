# Handoff

_Last updated: 2026-10-20. **Day 1 milestone complete.**_

## Goal
Build the MedFlow AI MVP in 8 days, following `docs/PLAN.md`. Next: Day 2 (appointments complete), after review.

## Current state
- Day 1 vertical slice is done and committed (`7a60c30`): appointments list + add form → `storage.py` → `instance/appointments.json`.
- `pytest`: 35/35 pass. Acceptance criteria S1–S6 all pass, in tests and against a real Flask server (curl: GET `/` 302, POST without token 400, invalid POST 400, valid POST 302; the record was in the JSON and still listed after a server restart).
- Browser check: 375px (light) and 1024px (dark). Not yet re-checked at 1280px.
- Git: local `main` only, nothing pushed. `instance/`, `.venv/`, `.env*` are gitignored.
- Venv: Python 3.14.5, Flask 3.1.3, pytest 8.4.2. Project folder: `Desktop\BettermindLabs_MedFlow`.

## Active files
- `medflow/__init__.py`: app factory, CSRF, date/time filters, 400/404 pages, `reset-demo`
- `medflow/storage.py`: load / save (atomic) / next_id / seed_missing / reset
- `medflow/appointments.py`: blueprint, `validate()`, list + create
- `medflow/templates/`: `base.html`, `_macros.html`, `appointments/list.html`, `error.html`
- `medflow/static/css/app.css`: design tokens (light + dark) and components
- `data/seed/appointments.json`, `tests/`

## Decisions made
- CSRF: per-session token, constant-time compare, form field or `X-CSRFToken` header. No Flask-WTF.
- Server-side validation is the single source of error messages (`novalidate` on forms).
- Atomic writes only; concurrent updates are last-write-wins (documented).
- No `app.js` until a feature needs it.

## Known gaps (not Day 1 scope)
- No edit/delete, status changes, follow-ups, reminders, or upcoming/past split yet.
- A corrupt data file shows a generic 500, not a friendly page.
- Nav has only "Appointments" until other features exist.

## Failed attempts / dead ends
- Mobile overflow from date/time inputs' intrinsic width. Fixed with `minmax(0, 1fr)` grid tracks and `min-width: 0` on inputs. Reuse this pattern.

## Next steps: Day 2 (criteria A1–A5)
1. Edit (reuse `validate()`) and delete with a confirmation (first small `app.js`); unknown id → 404.
2. Status (scheduled / completed / cancelled) and an upcoming vs. past split.
3. Follow-up tasks: a checklist per appointment.
4. `reminder_days_before` field and a "due reminders" helper (shown on the dashboard on Day 5).
5. Tests first for each; browser check at 375px and 1280px; `/code-review`; commit.
