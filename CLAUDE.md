# MedFlow AI

A personal healthcare navigation web app for a local demo: published procedure prices (MedPrice), appointment tracking, expense tracking, a dashboard, and AI-assisted explanations. MVP built in 8 days by two student developers. Product source: `MedFlow_One_Page_PRD.docx` (Team Helios, v1.0). Plan and acceptance criteria: `docs/PLAN.md`. Current state: `docs/HANDOFF.md`, so read it at the start of every session.

## Hard constraints (ask before breaking any of these)

- Stack: Python 3.11+, Flask, Jinja2, vanilla JavaScript, plain CSS, JSON files.
- No React, Next.js, Tailwind, build step, SQL/NoSQL database, or ORM.
- No new dependency (pip or CDN) without explicit approval. Runtime: Flask only. Dev: pytest.
- No plugins, MCP servers, background services, or external skills unless approved.
- **All data is fictional.** No real names, addresses, phone numbers, insurance IDs, or real patient data, including in tests and screenshots.
- No clinical advice. Never present a listed price as a guaranteed bill or a guaranteed coverage amount.
- The demo runs locally on 127.0.0.1. Nothing is deployed.

## Architecture

```
medflow/__init__.py     create_app(), config, CSRF check, CLI commands
medflow/storage.py      the ONLY module that reads or writes JSON files
medflow/<feature>.py    one Blueprint per feature: routes + that feature's validation and logic
medflow/templates/      base.html, _macros.html, one folder per feature
medflow/static/         css/app.css, js/app.js
data/                   committed fictional data: reference (prices, glossary) + demo seed
instance/               runtime user data (gitignored), copied from data/seed/ on first run
tests/                  pytest, one file per module
```

Rules:
- Routes never open files. They call `storage.load(name)` / `storage.save(name, records)`.
- Logic that is used by one feature lives in that feature's module. Move it to a shared place only when a second feature needs it.
- Reference data (`procedures`, `providers`, `prices`, `glossary`) is read-only at runtime.
- Server-rendered first. JavaScript only enhances pages that already work without it.
- No classes where a function will do. No base classes, repositories, service layers, or registries.

## Data conventions

- Each collection is a JSON list of flat objects in `<name>.json`.
- `id`: integer, assigned by `storage.next_id(records)` (max + 1).
- Dates are ISO `YYYY-MM-DD`, times `HH:MM` (24h). Timestamps ISO 8601.
- Money is stored as **integer cents** (`amount_cents`). Format only in templates.
- Writes are atomic: write a temp file in the same folder, then `os.replace`.
- **Concurrent updates are NOT protected.** Load → change → save is last-write-wins, so two simultaneous writes to one collection can lose a change. Acceptable for a single-user local demo; don't add locking unless asked.
- A missing file loads as `[]`. A corrupt file raises a clear error; never silently overwrite it.
- Prices always carry `price_type` (e.g. `cash`, `negotiated`, `list`), `source`, and `as_of`.

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
- Run with `--debug` only on 127.0.0.1.

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
flask --app medflow run --debug          # http://127.0.0.1:5000
flask --app medflow reset-demo           # restore instance/ from data/seed/
pytest
```
