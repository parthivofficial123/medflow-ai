# MedFlow AI: 8-day MVP plan

Goal: a polished, working local demo of the PRD's five MVP features, using fictional data only. The deadline beats scope. If a day slips, cut items marked *(stretch)* first, then simplify, but never skip tests or disclaimers.

PRD note: the PRD's timeline is 8 *weeks* (interviews, pilot users). This plan compresses the build into 8 *days*. User interviews and the five-user pilot are out of scope and stay in the PRD for later.

## MVP scope

| Feature | In scope | Out of scope (later) |
|---|---|---|
| **Appointments** | Add, edit, delete, list (upcoming / past). Fields: date, time, provider, location, reason, visit notes, status, reminder (days before), follow-up tasks (checklist) | Calendar view, clinic booking, email/SMS/push |
| **Reminders** | In-app only: due reminders show on the dashboard and as a banner on every page until dismissed | Notifications outside the app, background schedulers |
| **Expenses** | Add, edit, delete, list. Estimated, actual (may be unknown) and paid amounts kept separate; optional link to an appointment. Summary by category and month. See [Expense specification](#expense-specification-day-3) | Receipt upload, insurance claims, refunds |
| **MedPrice** | Plain-language search (aliases), compare like-for-like prices for one procedure across 4–6 fictional providers, show price type, what's included, source and source date, sample-data label, disclaimer, save a comparison. See [Price comparison specification](#price-comparison-specification-day-4) | Real CMS files, insurance estimates, maps |
| **Dashboard** | Next 3 appointments, due reminders, open follow-ups, saved comparisons, spending this month (estimated vs. actual) | Charts library, custom widgets |
| **AI assistance** | (1) Term matching: "knee scan" → "MRI, knee" via alias data. (2) Billing glossary: explain terms (deductible, CPT, EOB…) with a source link. Both deterministic and offline | LLM calls *(stretch, needs approval: behind `MEDFLOW_AI=1`, fictional data only, canned fallback)* |
| **Support** | "Report an issue" form saved to `feedback.json`; "Known limitations" section in README | Accounts, login, multi-user |

## Data files

Reference (read-only, committed in `data/`): `procedures.json`, `providers.json`, `prices.json` (shapes below), `glossary.json` (term, plain explanation, source_url).

User data (runtime in `instance/`, seeded from `data/seed/`): `appointments.json`, `expenses.json`, `saved.json`, `feedback.json`.

Every route that changes user data uses `storage.modify(name)` (load → change → save under one lock). Reference data is never written at runtime.

## Expense specification (Day 3)

**Record** (`expenses.json`):

| Field | Type | Meaning |
|---|---|---|
| `id` | int | `storage.next_id` |
| `date` | `YYYY-MM-DD` | Date of service. Decides which month the expense belongs to |
| `provider`, `description` | str | Free text, fictional |
| `category` | str | One of a fixed list: `visit`, `imaging`, `lab`, `pharmacy`, `dental`, `vision`, `therapy`, `other` |
| `estimated_cents` | int or `null` | What the user expected to pay. Optional |
| `actual_cents` | int or `null` | The billed amount. **`null` = not billed yet / unknown. `0` = billed and nothing owed.** These are different and must never be merged |
| `paid_cents` | int | What the user has paid so far. Defaults to 0 |
| `appointment_id` | int or `null` | Optional link (see integration rules) |
| `appointment_label` | str or `null` | Snapshot, e.g. "Knee MRI · Nov 4, 2026", taken when linked so the context survives a deleted appointment |
| `created_at`, `updated_at` | ISO timestamps | |

**Money input:** parse with `decimal.Decimal`, never `float`. Accept `120`, `120.5`, `120.50`, `$1,234.56` (strip `$`, commas and spaces). Reject: negatives, more than 2 decimal places, `NaN`/`Infinity`, anything non-numeric, and anything over $1,000,000. Store `int(amount * 100)` after checking it's exact. A blank actual amount means `null`, not 0.

**Validation:** at least one of estimated or actual is required. `paid_cents ≤ actual_cents` when the actual is known (no overpayments or refunds in the MVP). Payment before a bill arrives is allowed and is shown as "paid, not billed yet".

**Derived status** (computed, never stored): `Not billed yet` (actual is null), `Unpaid` (paid = 0), `Partly paid`, `Paid` (paid ≥ actual, including an actual of $0).

**Summary definitions.** Each number is its own line and is never added to another:

| Number | Definition | Label in the UI |
|---|---|---|
| Estimated | Σ `estimated_cents` where set | "Estimated" |
| Billed | Σ `actual_cents` where not null | "Billed (actual)" |
| Paid | Σ `paid_cents` | "Paid" |
| Unpaid recorded bills | Σ max(`actual_cents` − `paid_cents`, 0) where actual is known | "Unpaid recorded bills" (not "You owe": the app can't verify patient responsibility) |
| Pending estimates | Σ `estimated_cents` where actual is null | "Expected, not billed yet" |
| Estimate accuracy | Σ (`actual` − `estimated`) over records that have **both** | "Billed vs. estimate" |

Estimates never appear in "Unpaid recorded bills". When no expense in a group has a known bill, Billed shows "—", not $0.00. Totals are shown per category and for the current month (by service date).

## Price comparison specification (Day 4)

**`procedures.json`:** `id` (stable slug, e.g. `mri-knee-no-contrast`), `name`, `code` (optional, illustrative CPT-style code), `aliases` (search terms, lowercase), `description`.

**`providers.json`:** `id` (stable slug, e.g. `lakeside-imaging`), `name` (always ends with "(fictional)"), `city` (fictional), `type` (`hospital`, `imaging center`, `lab`, `clinic`).

**`prices.json`:** `id`, `procedure_id`, `provider_id`, `amount_cents`, `price_type`, `includes` (list of short strings, e.g. `["scan", "radiologist reading"]`), `source_label`, `source_url` (or `null`), `as_of` (`YYYY-MM-DD`, the source's own date), `sample: true`.

**Price types** (fixed list; each shows a one-line explanation):
- `cash`: the self-pay price
- `negotiated`: an example insurer-negotiated rate, not what any given plan pays
- `list`: the hospital's gross charge before any discounts

**When prices are comparable:** only prices with the same `procedure_id`, the same `price_type` and the same `includes` set are ranked against each other. The page groups prices by price type. Within a group, prices covering the same services are sorted cheapest first, and "Lowest in this group" appears only when there are at least 2. Prices covering different services are listed under "Covers different services" and are not ranked. The page never shows a "cheapest overall" across price types.

**Source and freshness:** every price shows its source label, its `as_of` date, and a link when `source_url` is set. Prices whose `as_of` is over 12 months older than today show "May be out of date".

**Sample data:** all prices are fictional. The page shows a banner "Sample prices for a demo. Not real providers or real prices", and each card carries a "Sample" badge. `source_url` never points to a real hospital's site. It is `null` (shown as "Fictional source for the demo") or a link to general public information about price transparency.

**Disclaimer:** "Published prices are estimates, not a guaranteed bill. Your cost depends on your insurance and the care you actually receive." It's always visible next to the prices.

**Saved comparisons** (`saved.json`): `id`, `procedure_id`, `price_type`, `provider_id` (optional), `saved_at`. They store IDs, never names or amounts, so they always show current data. A saved item whose procedure or provider no longer exists shows "No longer available" instead of an error.

## Feature integration rules

- **References are IDs:** expense → `appointment_id`; saved comparison → `procedure_id`, `provider_id`. The appointment `provider` stays free text in the MVP and doesn't link to `providers.json`.
- **Deleting an appointment never deletes expenses.** The delete confirmation says how many linked expenses there are and that they stay in Expenses. The delete writes `expenses.json` first (sets `appointment_id` to null, keeping `appointment_label`), then `appointments.json`. If the second write fails, the expenses are merely unlinked from an appointment that still exists, which is harmless.
- **Every page tolerates missing references.** An expense whose appointment is gone shows "Linked appointment was deleted" plus its label. This also covers the multi-file limit below.
- **The dashboard only reads data.** It imports helpers from the feature modules (`appointments.reminder_due`, the expense summary function, etc.). Feature modules never import the dashboard.
- **Multi-file limitation:** `storage` makes each file write atomic and serializes writes within one process, but a change touching two files is two writes, not a transaction. A crash between them can leave the files out of step. The order above keeps the worst case harmless. Anything needing true multi-file transactions would need a database, which is out of scope.

## Day-by-day

| Day | Deliverable | Done when |
|---|---|---|
| **1** | Skeleton + **vertical slice**: app factory, CSRF, `storage.py`, `base.html`, design tokens in `app.css`, appointments list + add form, seed data, tests | Acceptance criteria S1–S6 below pass |
| **2** | Appointments complete: edit, delete (with confirm), status, notes, follow-up tasks, reminder field; upcoming/past split; `reset-demo` command | A1–A5 pass |
| **3** | Expenses per the [specification](#expense-specification-day-3): CRUD, categories, Decimal money parsing, unknown vs. $0 actuals, paid amounts, link to appointment, summary | E1–E5 pass |
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
- **E1** CRUD works with validation: valid date, a category from the fixed list, money rules from the spec (Decimal parsing; negatives, >2 decimals, NaN and over-limit rejected; paid ≤ actual). Input is kept on error.
- **E2** Amounts are stored as integer cents and displayed as `$1,234.56`. Tests include `0.29` → 29 and `19.99` → 1999 (the float pitfalls).
- **E3** A blank actual amount is saved as `null` and shown as "Not billed yet"; an actual of `0` is shown as `$0.00` / "Paid". Tests cover both.
- **E4** The summary shows Estimated, Billed, Paid, "Unpaid recorded bills" and "Expected, not billed yet" as separate numbers, per category and for the current month. Tests check each definition against hand-computed totals, including that estimates never count toward unpaid bills.
- **E5** An expense can link to an appointment, and the appointment page lists its linked expenses. Deleting the appointment keeps the expenses, unlinked, with their label and a "Linked appointment was deleted" note.

### MedPrice
- **P1** Searching "knee scan", "knee MRI", or "MRI knee" finds the same procedure (by `procedure_id`). No match shows suggestions instead of an empty page.
- **P2** Prices are grouped by price type. Only prices with the same type and the same included services are ranked against each other (cheapest first). Every price shows its type, what it includes, its source and its source date. Prices over 12 months old are flagged.
- **P3** The disclaimer, the sample-data banner, and a "Sample" badge on each price are visible. No real provider names or real hospital URLs appear in the data.
- **P4** Saving a comparison stores IDs in `saved.json`, and it appears on the dashboard. A saved item pointing at a missing procedure shows "No longer available".
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
- **R2** No lost records: tests cover atomic writes, a restart, a corrupt file, and 20 concurrent writes all persisting.
- **R3** Every page works at 375px and 1280px, is keyboard-navigable with visible focus, and every input has a label.
- **R4** `/security-review` finds no unresolved high-severity issues.
- **R5** The only data anywhere in the repo is fictional; disclaimers are on the price and explanation pages.

## Approved decisions
1. Reminders are in-app only (no email/push) for the MVP.
2. "AI assistance" ships as deterministic alias matching + glossary; an LLM is a Day 6 stretch behind a flag.
3. Single user, no login.
4. `pytest` is the one dev dependency.
5. (Audit, Day 2.5) Writes go through `storage.modify`; dates and times are stored in canonical form; expense and price specifications above are final for Days 3–4.
