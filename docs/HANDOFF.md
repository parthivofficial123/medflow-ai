# Handoff

_Last updated: 2026-10-20. **Day 2 milestone complete. Waiting for review before Day 3.**_

## Goal
Build the MedFlow AI MVP in 8 days, following `docs/PLAN.md`. Next: Day 3 (expenses, E1–E4), only after approval.

## Current state
- Day 1 (slice) and Day 2 (appointment management) are done and committed locally. Nothing is pushed.
- `pytest`: 86/86 pass (35 Day 1 + 51 Day 2). Acceptance criteria A1–A5 pass.
- Browser-checked at 1280px and 375px: list (reminders, upcoming, past), detail, edit, delete confirmation. No horizontal scroll; every control is a 44px+ tap target (card title links use a full-card overlay).
- Flows checked by hand in the browser: tick a task, change status, reminder text updates.

## Day 2 features
- **Detail page** `/appointments/<id>`: facts, notes, Edit / Delete, status buttons, reminder panel, follow-up checklist.
- **Edit** `/appointments/<id>/edit`: reuses the add form's fields (`appointments/_fields.html`).
- **Delete**: separate confirmation page (`GET /<id>/delete`), so it works without JavaScript; lists how many tasks go with it.
- **Status**: scheduled / completed / cancelled. Cancelled is struck through with a grey pill; past cards get a grey date badge.
- **Upcoming vs. past**: today counts as upcoming; past is newest first.
- **Follow-up tasks**: add (validated, max 200 chars, input kept on error), tick/untick, remove. Task ids are per appointment.
- **Reminders (in-app)**: `reminder_days_before` ∈ {none, 0, 1, 2, 3, 7}. Due from N days before through the visit day, only while scheduled and not dismissed. Shown in a panel on the list page and the detail page. Changing the date or reminder turns a dismissed reminder back on.

## Active files
- `medflow/appointments.py`: routes, `validate()`, `reminder_due()`, `load_one()`, `today()` (patched in tests)
- `medflow/templates/appointments/`: `list.html`, `detail.html`, `edit.html`, `confirm_delete.html`, `_fields.html`
- `medflow/templates/_macros.html`: `field`, `select_field`, `error_summary`
- `medflow/static/css/app.css`: new button variants, panels, tasks, segmented status control, reminders, warning tokens
- `data/seed/appointments.json`: 6 fictional appointments (4 upcoming, 1 completed, 1 cancelled) with tasks and reminders
- `tests/test_appointments.py`

## Decisions made
- Still no `app.js`: delete uses a confirmation page instead of `confirm()`.
- Reminder choices are a fixed list, not free numbers, so the UI and validation stay simple.
- `today()` is a module function so tests pin the date to 2026-10-20.
- Day 1 records without `tasks` / `reminder_*` keep working (tested); no data migration needed.

## Known issues / gaps
- Seed dates are fixed. After 2026-10-23 the demo shows no due reminder until you edit one. Run `flask --app medflow reset-demo` to get the Day 2 demo data; your existing `instance/` file was left untouched.
- The reminder banner on every page (D3) and the dashboard come on Day 5.
- A corrupt data file still shows a generic 500 page.
- On phones the Status and Reminder panels come after the task list (columns stack).

## Failed attempts / dead ends
- Mobile overflow from date/time inputs: use `minmax(0, 1fr)` tracks and `min-width: 0`.
- `.page-header__jump` stayed visible on desktop because the later `.btn` rule had equal specificity. Fixed with `.page-header .page-header__jump`. Watch the rule order for utility classes.

## Next steps: Day 3 (after approval, criteria E1–E4)
1. `medflow/expenses.py` blueprint + `data/seed/expenses.json` (fictional).
2. Expense CRUD: date, provider, category (fixed list), description, estimated and actual amounts (entered in dollars, stored in cents), paid/unpaid, optional link to an appointment.
3. Summary: estimated vs. actual per category and for the current month.
4. Show linked expenses on the appointment detail page.
5. Add "Expenses" to the nav. Tests first; check 375px and 1280px; commit.
