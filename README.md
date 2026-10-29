# MedFlow AI

A student-built demo of personal healthcare navigation. Upload a **fictional** medical bill;
AI lists and explains each charge in plain language; you check and correct every line; the
charges you approve are saved as expenses. MedFlow also tracks appointments (with reminders
and follow-up tasks) and expenses (estimated vs. billed vs. paid, linked to appointments).

> **Fictional data only.** This is a demo, not a medical, billing or insurance service.
> Never upload a real bill or anyone's personal information. Bills are sent to the
> Google Gemini API free tier, whose inputs Google may review and use to improve its products.

## What works today

| Feature | State |
|---|---|
| Bill understanding (upload → AI extraction → editable review → save as expenses) | Working |
| Appointments: add, edit, delete, status, reminders, follow-up tasks | Working |
| Expenses: add, edit, delete, mark paid/unpaid, link to an appointment, monthly and category totals | Working |
| Google Sign-In (Supabase Auth) with per-user data protected by Row-Level Security | Working |
| Price search over real published prices ("MedPrice") | **Not built yet** (planned in `docs/PLAN.md`) |
| Dashboard | **Not built yet**; `/` opens the appointments page |

## How it is built

Python, Flask and Jinja templates, plain CSS and one small vanilla-JavaScript file. No build
step. Data lives in Supabase (Postgres + Auth); local JSON files are an offline mode for
development and tests. The AI only reads and explains: Python validates every amount and date,
does all money math in integer cents, and nothing is saved until the user approves it.

```
app.py              Vercel entry point
medflow/            the Flask app: one module per feature, storage.py for all data access,
                    bill_ai.py for the only AI call, templates/
public/static/      CSS and JS (in public/ so Vercel can serve them)
supabase/           schema.sql, isolation_test.sql and setup steps (run by hand)
data/seed/          fictional demo data each new user starts with
data/sample_bills/  three fictional PDF bills, one with a prompt-injection test
scripts/            benchmark_bills.py (makes real Gemini calls; run by hand only)
tests/              pytest suite; fakes the AI and Supabase, never uses the network
docs/               PLAN.md (spec), HANDOFF.md (current state), GITHUB_READINESS.md (audit)
```

## Run it locally (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
flask --app medflow run --debug
```

Open http://localhost:5000. On macOS/Linux use `source .venv/bin/activate` and `cp`.

- **Offline (JSON) mode** is the default (`MEDFLOW_STORAGE=json`): no sign-in, data in
  `instance/`, created from `data/seed/`. `flask --app medflow reset-demo` restores the demo
  data. JSON mode has **no authentication**, so only run it on localhost.
- **Supabase mode** (`MEDFLOW_STORAGE=supabase`): follow [`supabase/README.md`](supabase/README.md)
  to create the tables, turn on Google Sign-In and set `SUPABASE_URL`,
  `SUPABASE_PUBLISHABLE_KEY` and `MEDFLOW_SECRET_KEY`. Use the publishable key only, never the
  secret key; the app refuses to start with one.
- **Bill analysis** needs `GEMINI_API_KEY` (a free key from Google AI Studio). Without it the
  rest of the app works, and uploading a bill says AI analysis isn't configured.
- Use `--debug` only on localhost, never together with `--host`.

## Tests

```
pytest
```

The suite runs offline: it replaces Gemini with a fake and Supabase with
`tests/fake_supabase.py`, which enforces per-user access like Row-Level Security does. It is
not a test of the real database's policies; `supabase/isolation_test.sql` checks those on a
real project with two accounts.

## Limitations

- A demo for fictional data, built in 8 days. Not reviewed for HIPAA or any other compliance.
- Sessions last as long as the Supabase access token (1 hour by default); then you sign in again.
- AI extraction can be wrong. The review page shows what the AI read next to the editable
  values, flags unreadable or negative amounts, and compares the total with the bill's own.
- Gemini free-tier capacity varies. A slow or busy service is retried a little and then gives a
  clear error after about 45 seconds.
- More limits and their reasons: `docs/HANDOFF.md` and `docs/GITHUB_READINESS.md`.

## Deployment

Prepared for Vercel (`app.py`, `public/`, `.vercelignore`) but **not deployed**. See
"Deployment findings" in `docs/GITHUB_READINESS.md` before deploying.
