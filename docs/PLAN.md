# MedFlow AI: 8-day MVP plan

Goal: a polished, working local demo of the PRD's five MVP features, using fictional data only. The deadline beats scope. If a day slips, cut items marked *(stretch)* first, then simplify, but never skip tests or disclaimers.

PRD note: the PRD's timeline is 8 *weeks* (interviews, pilot users). This plan compresses the build into 8 *days*. User interviews and the five-user pilot are out of scope and stay in the PRD for later.

## MVP scope

| Feature | In scope | Out of scope (later) |
|---|---|---|
| **Appointments** | Add, edit, delete, list (upcoming / past). Fields: date, time, provider, location, reason, visit notes, status, reminder (days before), follow-up tasks (checklist) | Calendar view, clinic booking, email/SMS/push |
| **Reminders** | In-app only: due reminders show on the dashboard and as a banner on every page until dismissed | Notifications outside the app, background schedulers |
| **Expenses** | Add, edit, delete, list. Fields: date, provider, category, description, estimated amount, actual amount, paid/unpaid, optional link to an appointment. Summary: estimated vs. actual by category and month | Receipt upload, insurance claims |
| **MedPrice** | Plain-language search (aliases), compare prices for one procedure across 4–6 fictional providers, show price type + source + as-of date, disclaimer, save a comparison or provider | Real CMS files, insurance estimates, maps |
| **Dashboard** | Next 3 appointments, due reminders, open follow-ups, saved comparisons, spending this month (estimated vs. actual) | Charts library, custom widgets |
| **AI assistance** | (1) Term matching: "knee scan" → "MRI, knee" via alias data. (2) Billing glossary: explain terms (deductible, CPT, EOB…) with a source link. Both deterministic and offline | LLM calls *(stretch, needs approval: behind `MEDFLOW_AI=1`, fictional data only, canned fallback)* |
| **Support** | "Report an issue" form saved to `feedback.json`; "Known limitations" section in README | Accounts, login, multi-user |

## Data files

Reference (read-only, committed in `data/`): `procedures.json` (name, code, aliases), `providers.json`, `prices.json` (procedure_id, provider_id, amount_cents, price_type, source, as_of), `glossary.json` (term, plain explanation, source_url).

User data (runtime in `instance/`, seeded from `data/seed/`): `appointments.json`, `expenses.json`, `saved.json`, `feedback.json`.

## Day-by-day

| Day | Deliverable | Done when |
|---|---|---|
| **1** | Skeleton + **vertical slice**: app factory, CSRF, `storage.py`, `base.html`, design tokens in `app.css`, appointments list + add form, seed data, tests | Acceptance criteria S1–S6 below pass |
| **2** | Appointments complete: edit, delete (with confirm), status, notes, follow-up tasks, reminder field; upcoming/past split; `reset-demo` command | A1–A5 pass |
| **3** | Expenses: CRUD, categories, link to appointment, estimated vs. actual summary | E1–E4 pass |
| **4** | MedPrice: reference data (≈10 procedures, 5 providers), alias search, comparison cards, disclaimer, save comparison. **Checkpoint: `/security-review`** | P1–P5 pass |
| **5** | Dashboard + reminders banner. Full UI polish pass (spacing, type, empty states, focus styles) | D1–D4 pass |
| **6** | Glossary + term-matching explanations, "Report an issue" form. *(stretch)* LLM explanations if approved | G1–G3 pass |
| **7** | Hardening: `/security-review`, `/code-review` on the whole app, accessibility and 375px checks, end-to-end release test, fix only what those find | R1–R5 pass |
| **8** | Demo prep: README (setup, screenshots, known limitations), fresh-clone run-through, rehearse the demo script, code freeze by midday | Demo runs from a clean clone in under 5 minutes |

Daily rhythm: plan → failing test → implement → browser check → `pytest` → `/code-review` → commit → update `HANDOFF.md`.

## Acceptance criteria

### Vertical slice (Day 1)
- **S1** `flask --app medflow run --debug` starts with no errors; `/` redirects to `/appointments`.
- **S2** `GET /appointments` renders the seeded fictional appointments, sorted by date then time.
- **S3** Submitting the add form with valid data saves to `instance/appointments.json`, redirects back, shows a success message, and the new row appears. It is still there after a server restart.
- **S4** Submitting with a missing date or reason shows inline errors, returns HTTP 400, keeps what was typed, and writes nothing.
- **S5** A POST without a CSRF token is rejected (400).
- **S6** `pytest` passes: storage round-trip, atomic save, missing file → `[]`, corrupt file → error, plus S2–S5 through the Flask test client.

### Appointments
- **A1** Edit and delete work; deleting asks for confirmation; unknown id → 404.
- **A2** Upcoming and past appointments are listed separately; cancelled ones are visibly marked.
- **A3** Follow-up tasks can be added and checked off per appointment.
- **A4** An appointment with `reminder_days_before = N` appears as due from N days before its date until the date passes or it's dismissed.
- **A5** `reset-demo` restores the seed data.

### Expenses
- **E1** CRUD works with validation (amounts ≥ 0, valid date, a category from the fixed list).
- **E2** Amounts are entered as dollars, stored as cents, and displayed as `$1,234.56`.
- **E3** The summary shows estimated vs. actual totals per category and for the current month, and the totals match the records.
- **E4** An expense can link to an appointment, and the appointment shows its linked expenses.

### MedPrice
- **P1** Searching "knee scan", "knee MRI", or "MRI knee" finds the same procedure. No match shows suggestions instead of an empty page.
- **P2** The comparison lists every provider price for that procedure, cheapest first, each showing price type, source, and as-of date.
- **P3** The disclaimer "Published prices are estimates, not a guaranteed bill" is visible next to the prices.
- **P4** Saving a comparison stores it in `saved.json`, and it appears on the dashboard.
- **P5** Search returns in under 3 seconds on the demo dataset (it will be milliseconds).

### Dashboard
- **D1** Shows the next 3 upcoming appointments, due reminders, open follow-ups, saved comparisons, and this month's spending.
- **D2** Every section has a useful empty state with a link to add data.
- **D3** Due reminders show as a dismissible banner on every page.
- **D4** The page loads in under 3 seconds.

### AI assistance and support
- **G1** Glossary terms in price and expense pages link to a plain-language explanation with a source link.
- **G2** Explanations carry a "general information, not medical or financial advice" note.
- **G3** "Report an issue" saves to `feedback.json` and confirms to the user.

### Release (PRD release criteria, adapted)
- **R1** End-to-end in one browser session: search a procedure → view source-backed comparison → save it → add an appointment → see its reminder → log an expense. Automated as one test and rehearsed by hand.
- **R2** No lost records: tests cover atomic writes, a restart, and a corrupt file.
- **R3** Every page works at 375px and 1280px, is keyboard-navigable with visible focus, and every input has a label.
- **R4** `/security-review` finds no unresolved high-severity issues.
- **R5** The only data anywhere in the repo is fictional; disclaimers are on the price and explanation pages.

## Decisions awaiting approval
1. Reminders are in-app only (no email/push) for the MVP.
2. "AI assistance" ships as deterministic alias matching + glossary; an LLM is a Day 6 stretch behind a flag.
3. Single user, no login.
4. Add `pytest` as the one dev dependency on Day 1.
