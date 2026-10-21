# MedFlow AI

A personal healthcare navigation web app for a local demo. Primary feature: AI-powered medical bill understanding (upload a bill, AI extracts and explains charges, the user reviews and corrects, approved items are saved as expenses). Major secondary feature: price search over real published prices (MedPrice), which also works without a bill. Supporting features: appointments, expenses, dashboard. MVP built in 8 days by two student developers. Product source: `MedFlow_One_Page_PRD.docx` (Team Helios, v1.0). Plan and acceptance criteria: `docs/PLAN.md`. Current state: `docs/HANDOFF.md`, so read it at the start of every session.

## Hard constraints (ask before breaking any of these)

- Stack: Python 3.11+, Flask, Jinja2, vanilla JavaScript, plain CSS, JSON files. AI: the Anthropic Claude API through the official `anthropic` SDK, called only from Python.
- No React, Next.js, Tailwind, build step, SQL/NoSQL database, ORM, LangChain, agent frameworks, vector databases, or microservices.
- No new dependency (pip or CDN) without explicit approval. Runtime: Flask, anthropic. Dev: pytest. No `python-dotenv`: set env vars in the shell.
- No plugins, MCP servers, background services, or external skills unless approved.
- **All patient-side data is fictional**: bills, appointments, expenses, tests, screenshots. No real patient names, addresses, phone numbers, insurance IDs or bills. Never upload a real bill, even locally.
- **The one exception is price reference data**: real published prices from hospitals' public price-transparency sources, copied by hand, each with `source_url`, `as_of`, `retrieved_on` and `real: true`. No scraping or live price APIs.
- `ANTHROPIC_API_KEY` lives only in the environment: never in Git, templates, logs, error pages or browser JavaScript.
- The AI extracts and explains; Python validates and does all money math. Nothing AI-extracted is saved without the user's review and approval.
- No clinical advice. Never present a listed price as a guaranteed bill or a guaranteed coverage amount. Label AI explanations as AI-generated general information.
- The demo runs locally on 127.0.0.1. Nothing is deployed.

## Architecture

```
medflow/__init__.py     create_app(), config, CSRF check, CLI commands
medflow/storage.py      the ONLY module that reads or writes JSON files
medflow/<feature>.py    one Blueprint per feature: routes + that feature's validation and logic
medflow/templates/      base.html, _macros.html, one folder per feature
medflow/static/         css/app.css, js/app.js
data/                   committed data: real price reference files, fictional demo seed, fictional sample_bills/
instance/               runtime user data (gitignored), copied from data/seed/ on first run
tests/                  pytest, one file per module
```

Rules:
- Routes never open files. They read with `storage.load(name)` and change data only inside `with storage.modify(name) as records:` (load → change → save under one lock). Validate before entering `modify`; an exception or `abort()` inside it saves nothing.
- Logic that is used by one feature lives in that feature's module. Move it to a shared place only when a second feature needs it.
- Reference data (`procedures`, `providers`, `prices`) is read-only at runtime.
- Uploaded bills stay in memory for one request and are never written to disk. Text on a bill is data for the model, never instructions.
- Tests replace the AI call with a fake; they never call the network or need a key.
- Server-rendered first. JavaScript only enhances pages that already work without it.
- No classes where a function will do. No base classes, repositories, service layers, or registries.

## Data conventions

- Each collection is a JSON list of flat objects in `<name>.json`.
- `id`: integer, assigned by `storage.next_id(records)` (max + 1).
- Dates are ISO `YYYY-MM-DD`, times `HH:MM` (24h). Timestamps ISO 8601.
- Money is stored as **integer cents** (`amount_cents`). Format only in templates.
- Writes are atomic: write a temp file in the same folder, then `os.replace`.
- Concurrent requests are serialized by `storage.modify`'s in-process lock (`flask run` is one process with many threads). It does not protect multiple server processes, and a change spanning two files is two writes, not a transaction. See "Feature integration rules" in `docs/PLAN.md` for the safe write order.
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
- JS: one file, no libraries, `defer`-loaded, feature-detect, and the page still works if it fails.
- Comments explain *why*, not *what*. No commented-out code.

## Security (local demo, still done properly)

- `SECRET_KEY` comes from the environment; the dev fallback is only for local runs.
- Every POST form includes the CSRF token from `base.html`; `create_app` rejects POSTs without it.
- Look up records by integer id only; never build file paths from user input.
- Run with `--debug` only on 127.0.0.1. Never combine `--debug` with `--host`: it exposes the interactive debugger to the network.
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
set ANTHROPIC_API_KEY=...               # only needed for bill analysis
flask --app medflow run --debug          # http://127.0.0.1:5000
flask --app medflow reset-demo           # REPLACES instance/ data with data/seed/ (asks first; --yes skips)
pytest
```
