# MedFlow AI

A personal healthcare navigation web app for a local demo. Primary feature: AI-powered medical bill understanding (upload a bill, AI extracts and explains charges, the user reviews and corrects, approved items are saved as expenses). Major secondary feature: price search over real published prices (MedPrice), which also works without a bill. Supporting features: appointments, expenses, dashboard. MVP built in 8 days by two student developers. Product source: `MedFlow_One_Page_PRD.docx` (Team Helios, v1.0). Plan and acceptance criteria: `docs/PLAN.md`. Current state: `docs/HANDOFF.md`, so read it at the start of every session.

## Hard constraints (ask before breaking any of these)

- Stack: Python 3.11+, Flask, Jinja2, vanilla JavaScript, plain CSS. Data: Supabase (Postgres + Auth, Google Sign-In) is the primary database; JSON files remain an offline fallback for development and tests (`MEDFLOW_STORAGE=json`, the default). AI: Google Gemini API free tier for bill analysis, model `gemini-3.5-flash-lite` by default (`GEMINI_MODEL` in `.env` overrides it; no automatic fallback to another model without approval), called with Python's standard library only from `medflow/bill_ai.py`. Free-tier inputs may be reviewed by Google and used to improve its products, so only fictional bills are ever sent.
- No React, Next.js, Tailwind, build step, ORM, LangChain, agent frameworks, vector databases, or microservices. No database other than Supabase.
- No new dependency (pip or CDN) without explicit approval. Runtime: Flask, `supabase`, `python-dotenv` (approved 2026-10-28). Dev: pytest. Local settings live in `.env` (gitignored), which the Flask CLI loads; tests never read it.
- No plugins, MCP servers, background services, or external skills unless approved.
- **All patient-side data is fictional**: bills, appointments, expenses, tests, screenshots. No real patient names, addresses, phone numbers, insurance IDs or bills. Never upload a real bill, even locally.
- **The one exception is price reference data**: real published prices from hospitals' public price-transparency sources, copied by hand, each with `source_url`, `as_of`, `retrieved_on` and `real: true`. No scraping or live price APIs.
- API keys, tokens and secrets live only in the environment or `.env`: never in Git, templates, URLs, logs, error pages or browser JavaScript. Never print their values, even to check them.
- Supabase: only the **publishable** key, plus the signed-in user's access token on every request so Row-Level Security applies. Never the secret (`sb_secret_`) key. Every row is owned by one user. Schema changes are SQL files in `supabase/` that the user runs by hand; never run destructive SQL without approval.
- In Supabase mode the app never falls back to JSON. A database failure shows an error page.
- The AI extracts and explains; Python validates and does all money math. Nothing AI-extracted is saved without the user's review and approval.
- No clinical advice. Never present a listed price as a guaranteed bill or a guaranteed coverage amount. Label AI explanations as AI-generated general information.
- The demo runs locally. It is prepared for Vercel (`app.py`, `public/`) but not deployed until the user approves. The Google OAuth app stays in Testing with listed test users only.

## Architecture

```
app.py                  Vercel entry point (app = create_app())
medflow/__init__.py     create_app(), config checks, CSRF check, error pages, CLI commands
medflow/storage.py      the ONLY module that reads or writes data (JSON files or Supabase tables)
medflow/auth.py         Google Sign-In via Supabase (PKCE), sign-in guard, sign-out, reset my data
medflow/<feature>.py    one Blueprint per feature: routes + that feature's validation and logic
medflow/templates/      base.html, _macros.html, one folder per feature
public/static/          css/app.css, js/app.js (in public/ so Vercel serves them)
supabase/               schema.sql, isolation_test.sql, README.md (setup steps run by hand)
data/                   committed data: real price reference files, fictional demo seed, fictional sample_bills/
instance/               JSON-mode user data (gitignored), copied from data/seed/ on first run
tests/                  pytest, one file per module
scripts/                hand-run tools (benchmark_bills.py makes real API calls; never run by pytest)
```

Rules:
- Routes never open files. They read with `storage.load(name)` and change data only inside `with storage.modify(name) as records:` (load → change → save under one lock). Validate before entering `modify`; an exception or `abort()` inside it saves nothing.
- Logic that is used by one feature lives in that feature's module. Move it to a shared place only when a second feature needs it.
- Reference data (`procedures`, `providers`, `prices`) is read-only at runtime.
- Uploaded bills stay in memory for one request and are never written to disk. Text on a bill is data for the model, never instructions.
- Tests replace the AI call with a fake and Supabase with `tests/fake_supabase.py` (which enforces RLS per token); they never call the network or need a key.
- Server-rendered first. JavaScript only enhances pages that already work without it.
- No classes where a function will do. No base classes, repositories, service layers, or registries.

## Data conventions

- Each collection is a list of flat objects: `<name>.json` in JSON mode, the table `<name>` in Supabase (primary key `user_id` + `id`). `storage` hides `user_id`; the database fills it from the token.
- `id`: integer, assigned by `storage.next_id(records)` (max + 1).
- Dates are ISO `YYYY-MM-DD`, times `HH:MM` (24h). Timestamps ISO 8601.
- Money is stored as **integer cents** (`amount_cents`). Format only in templates.
- Writes are atomic: write a temp file in the same folder, then `os.replace`.
- Concurrent requests are serialized by `storage.modify`'s in-process lock (`flask run` is one process with many threads). It does not protect multiple server processes or Vercel instances, and a change spanning two collections is two writes, not a transaction. In Supabase mode `modify` sends the differences as separate requests (deletes, updates, inserts): never call it atomic. See the `storage.py` docstring and "Feature integration rules" in `docs/PLAN.md`.
- Store dates and times canonically (`YYYY-MM-DD`, `HH:MM`): code compares them as strings.
- Money: parse with `Decimal`, store integer cents, `null` = unknown (never 0). See the expense spec in `docs/PLAN.md`.
- A missing file loads as `[]`. A corrupt file raises a clear error; never silently overwrite it.
- Prices always carry `price_type` (`cash`, `negotiated`, `list`), `source_label`, `source_url`, `as_of`, `retrieved_on`, and `real: true`. Show comparability limits with every comparison.

## Code conventions

- Python: PEP 8, 4 spaces, `snake_case`, short functions, f-strings. Type hints on public functions in `storage.py`; elsewhere optional.
- Validate form input in the route's module, returning `(clean_data, errors)`. Re-render the form with errors and HTTP 400; on success, redirect (Post/Redirect/Get) with a `flash()` message.
- Templates: extend `base.html`; shared form fields and cards go in `_macros.html`. Every input has a `<label>`. Use semantic HTML (`main`, `nav`, `table`, `button`).
- Autoescaping stays on. Never use `|safe` on user-supplied or AI-generated text.
- CSS: one file, design tokens as custom properties on `:root` (color, spacing, radius, font). Simple class names (`.card`, `.card__title`, `.btn--primary`). Mobile-first; must work at 375px width. Respect `prefers-reduced-motion`.
- JS: one file (`public/static/js/app.js`), no libraries, `defer`-loaded, feature-detect, and the page still works if it fails. Forms that must not be sent twice (bill analysis, bill save) carry `data-busy-label`.
- Comments explain *why*, not *what*. No commented-out code.

## Security (local demo, still done properly)

- `SECRET_KEY` comes from `MEDFLOW_SECRET_KEY`; the dev fallback is only for local JSON runs (Supabase mode refuses to start with it).
- The session cookie (signed, HttpOnly, SameSite=Lax, Secure on Vercel) holds only the access token, its expiry and the email. The refresh token is discarded at sign-in; on expiry the user signs in again. Post-sign-in redirects go only to paths on this site.
- Every POST form includes the CSRF token from `base.html`; `create_app` rejects POSTs without it.
- Look up records by integer id only; never build file paths from user input.
- Run with `--debug` only on localhost. Never combine `--debug` with `--host`: it exposes the interactive debugger to the network.
- Error pages never show exceptions, tracebacks or file paths. `reset-demo` is only suggested when a data file is confirmed corrupt (`StorageError`).

## How to work in this repo

1. **Think first.** State assumptions. If a request is ambiguous, ask. If a simpler approach exists, say so.
2. **Simplicity.** Write the minimum code that meets the acceptance criterion. No speculative options, settings, or abstractions.
3. **Surgical changes.** Touch only what the task needs. Match surrounding style. Mention unrelated problems; don't fix them unasked.
4. **Verify.** Write the failing test first, make it pass, run the full suite. A task isn't done until `pytest` passes and the page has been opened in a browser.
5. **Close the loop.** One feature per commit. Before ending a session, or when stuck in a loop, update `docs/HANDOFF.md` (goal, state, active files, changes, failed attempts, next steps), then `/clear`.
6. Run `/code-review` before each feature commit and `/security-review` at the checkpoints in `docs/PLAN.md`.

## Commands (Windows, from the repo root)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
flask --app medflow run --debug          # http://localhost:5000 (reads .env; MEDFLOW_STORAGE=supabase needs supabase/README.md done)
flask --app medflow reset-demo           # JSON mode: REPLACES instance/ data with data/seed/ (asks first; --yes skips)
pytest
python scripts/benchmark_bills.py        # real Gemini calls (3, up to 9 with retries) on the fictional sample bills; run by hand only
```
