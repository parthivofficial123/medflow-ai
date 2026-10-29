# Handoff

_Last updated: 2026-10-28. **Supabase and Google Sign-In verified by the user on the real project. Bill analysis now uses `gemini-3.5-flash-lite` (3/3 benchmark, 1–2 s per bill), with bounded retries and a double-submit guard.**_

## Goal
Demo on Friday 2026-10-30: upload a fictional bill → Gemini extracts and explains → review and fix → save to expenses, each user signed in with Google and seeing only their own data in Supabase. Then Vercel (only when approved) and, if time allows, a small price search.

## Current state
- `pytest`: all tests pass (JSON mode plus Supabase mode against `tests/fake_supabase.py`). Not pushed or deployed.
- **Model:** `gemini-3.5-flash-lite` (`bill_ai.DEFAULT_MODEL`); set `GEMINI_MODEL` in `.env` to try another (no automatic fallback). An invalid name shows "isn't set up correctly" before any request.
- **Benchmark on the lite model (real API, 2026-10-28):** first run 2 of 3 perfect: bill 03's provider came back as "Harbor Urgent Care", dropping "(fictional)" (every item, amount, date, bill date and total was right). It was right in 2 reruns, so it was intermittent. The prompt now asks for the provider name "exactly as written, including any words in parentheses"; after that, 3 of 3 perfect (1.7–1.9 s each) and bill 03's provider correct in 2 more runs. Small sample: keep an eye on it; the provider field is editable on the review page. The prompt-injection bill kept its real amounts in every run, and explanations stayed general (no advice).
- **Retries** (`bill_ai.py`): 5xx and timeouts retried with backoff (2 s, 4 s + jitter); 429 only if Google asks for 10 s or less; max 3 requests, 20 s per attempt, 45 s total.
- **Double-submit guard** (`public/static/js/app.js`, the app's first JS): forms with `data-busy-label` (bill upload, bill save) disable their button, show "Reading your bill…"/"Saving…" and ignore further submits; the Back button restores them. Browser-checked with real Gemini: three submit attempts sent one analysis request; three on Save saved 4 expenses once. Without JS the forms still work. Server side, each review page carries a one-time `review_id`; the session remembers the last 20 saved, so Back + Save again adds nothing ("already saved").
- **Supabase backend** (`storage.py`, `MEDFLOW_STORAGE=supabase`): per-request client with the publishable key and the user's access token (RLS does the isolation; no secret key anywhere). `load` hides `user_id`; `modify` diffs before/after and sends deletes → updates (changed fields only) → inserts. Errors become `DatabaseError` (503 page, "may not have been saved, reload to check") or `SignedOut` (token rejected → sign-in page). Never falls back to JSON.
- **Sign-in** (`auth.py`): POST `/login` → Supabase authorize URL with a PKCE S256 challenge (verifier in the signed session) → `/auth/callback` exchanges the code, clears the session, keeps only access token + expiry + email, discards the refresh token, seeds demo data for a user with no data, and redirects to the saved page (same-site paths only). POST `/logout` revokes the session at Supabase. Guard on every other page in Supabase mode; tokens within 60 s of expiry count as expired. "Reset my demo data" (footer) replaces only the current user's data, after confirming.
- **Config checks** (`create_app`): refuses to start with an unknown `MEDFLOW_STORAGE`, a missing/invalid `SUPABASE_URL` or key, a `sb_secret_` key, or the dev `SECRET_KEY` in Supabase mode; trims `SUPABASE_URL` to its origin (the `.env` value ends in `/rest/v1/`). On Vercel (`VERCEL=1`): Supabase mode required, ProxyFix, Secure cookie.
- **Vercel prep (not deployed):** `app.py`, static files in `public/static/`, `.vercelignore`, uploads capped at 4 MB.
- **SQL:** `supabase/schema.sql` (create-only; composite PK `user_id, id`; checks mirror validation; FK keeps expense links inside one user and clears them on delete; RLS with 4 policies per table; anon has no grants). `supabase/isolation_test.sql` (rolled back; pass/fail table).
- Browser-checked: real config → sign-in page → Supabase authorize URL (Google not enabled yet, as expected); fake Supabase → signed-in header at 375px and 1280px, reset page, sign-out. Cookie is HttpOnly; no token in the HTML.

## Gemini timeouts (investigated 2026-10-28 evening)
- Symptom: a fictional one-page PDF upload showed "didn't respond in time" (server log: two uploads, each "Gemini timed out after 60 seconds").
- Measured: DNS + TLS to Google 0.12 s; `gemini-3.8-flash` exists; request format is correct (benchmark 3/3 earlier). A one-line text call with no PDF hung 180 s; a sample-bill call got HTTP 503 "model is currently experiencing high demand"; another succeeded in 81 s for 1,321 tokens (queueing, not work).
- Root cause: `gemini-3.8-flash` free tier overloaded on Google's side (503s and long hangs), and our 60 s limit was below its current latency. Not the PDF, the network or our code.
- Fix then: bounded retries (first 90 s / 150 s, now 20 s / 45 s for the lite model). Then the switch to `gemini-3.5-flash-lite` (approved; see Current state).
- Known limits: urllib's timeout is per socket read, so a trickling reply could outrun the 45 s limit; a timed-out request may still count against free-tier quota; the "45 seconds" hint isn't derived from `TOTAL_SECONDS`; the lite model is a preview of how free-tier capacity behaves today, not a guarantee for Friday; the 20 s attempt limit was measured on small text PDFs only, so a large photo of a bill could need longer (the benchmark has no PNG/JPEG bills yet); without JS, a fast double-click on "Read this bill" still sends two analyses.

## Next steps
1. Rehearse the demo with the real bill flow on Supabase; run `scripts/benchmark_bills.py` once on Friday morning to confirm the model is responsive.
2. Supabase sign-in, persistence and linking were verified by the user on the real project; still to run: two accounts + `isolation_test.sql`.
3. `/security-review` checkpoint before any deploy. Vercel only after the user approves (set env vars in Vercel, add the Vercel callback URL in Supabase).
4. Small price search (Day 6 spec) if time allows.

## Known limitations (Supabase)
- `modify` is several requests, not a transaction; see the `storage.py` docstring and PLAN.md "Feature integration rules".
- A user who deletes all their data gets the demo data again at the next sign-in (seeding is "no data at all").
- Sessions end when the access token expires (default 1 hour), and a form posted after that is lost. `supabase/README.md` step 4 explains how to lengthen it for the demo.
- `reset-demo` is JSON-only; Supabase users reset from the app.
- From code review, left for after the demo: seeding that fails half-way isn't retried (Reset fixes it); two simultaneous first sign-ins can hit a duplicate-id 503; starting sign-in in two tabs fails the first; `modify`'s lock is held across Supabase requests; a new Supabase client (no connection reuse) per request; "4 MB" text isn't derived from `MAX_UPLOAD_BYTES`.

## Day 4 features
- `medflow/bill_ai.py`: the only module that talks to an AI provider. `PROMPT` (bill text is data, not instructions; copy amounts exactly), `ANSWER_SCHEMA` (all strings), `call_model()` (provider stub), `extract()` (JSON parse → `AIError` on failure).
- `medflow/bills.py`: `/bills/` upload → file check by leading bytes + extension (PDF/PNG/JPEG) → `extract` → `check_answer` → read-only review page. Saves nothing.
- `check_answer`: rejects wrongly shaped answers; `null` optional fields mean "not shown"; amounts through `expenses.parse_money`, dates through `dates.check_date`; unreadable or negative amounts (`-$50`, `($50)`) are flagged, never guessed; items total only when every amount parsed; compares with the bill's printed total; flags an unreadable total. Text trimmed; max 100 items.
- Uploads stay in memory: `MemoryUploadRequest` in `__init__.py` overrides Werkzeug's `_get_file_stream` so no upload spills to a temp file. `MAX_CONTENT_LENGTH` = 4 MB (was 5; Vercel limit) with a friendly 413 page.
- `data/sample_bills/`: 3 fictional PDFs, including `03_prompt_injection_test.pdf` for the Day 5 security review. `.gitattributes` marks PDFs binary (line-ending conversion would corrupt them).

## Known limitations (Day 4)
- The 413 message mentions a file even on other forms (only reachable with 4 MB+ text).
- The upload field is written by hand; the `field` macro doesn't support file inputs.
- Adjustments and payments on a bill are flagged, not handled.

## Day 3 features
- **Money:** `expenses.parse_money()` reads input with `Decimal` behind an ASCII-only regex (`120`, `120.5`, `$1,234.56`); rejects negatives, more than 2 decimals, `NaN`/`Infinity`/`1e3`, misplaced commas (`1,23`), non-ASCII digits, and anything over $1,000,000. Stored as integer cents and displayed by the `money` filter using integer math only.
- **Unknown vs. $0:** a blank Billed amount is `null` ("Not billed yet"); `0` is a real $0 bill ("Paid"). Summaries show "—" for Billed when a group has no bills yet.
- **Separate totals** (`expenses.summarize`): Estimated, Billed, Paid, **Unpaid recorded bills**, Expected-not-billed-yet, and billed-vs-estimate only over expenses with both. Estimates never count as unpaid bills. Shown for the current month (tiles) and all time by category (table).
- **Status** (derived): Not billed yet / Unpaid / Partly paid / Paid. "Mark paid" sets paid = billed; "Mark unpaid" sets paid = 0.
- **CRUD:** add, edit (prefilled in dollars), delete with a confirmation page; all writes via `storage.modify`.
- **Appointments link:** optional `appointment_id` plus a label snapshot. The appointment page lists its expenses and has an "Add expense for this visit" link (prefills date, provider, link). Deleting an appointment unlinks its expenses first, then deletes it; the expenses keep their label and show "Linked appointment was deleted". A dangling id (crash between the two writes) is tolerated.
- **Shared code:** `medflow/dates.py` (`today()`, `check_date()`), used by both features. Tests pin the date in `tests/conftest.py`.
- **Layout:** on phones the nav moves to its own row under the logo (and scrolls sideways if more links are added); stat tiles show two per row.

## Problems found and fixed during Day 3
- `parse_money` accepted non-ASCII digits (`٣` → 3) because `\d` is Unicode-aware. Fixed with `re.ASCII`; regression test added.
- A category with no bills showed "Billed $0.00", indistinguishable from a real $0 bill. Now shows "—" (`billed_count`).
- The header wrapped "MedFlow AI" onto two lines at 375px once a second nav link existed. Fixed with a mobile nav row.
- The appointment link on expense cards was a 19px tap target. Now 44px.
- The Billed field's longer hint misaligned the amount inputs. Hints moved to the fieldset.

## Known limitations
- Payments are a single running "paid so far" amount, not a payment history. "Mark unpaid" resets a partial payment to 0.
- No refunds or overpayments (paid can't exceed billed).
- "Unpaid recorded bills" reflects what the user entered; it is not verified patient responsibility. The page says so.
- Storage lock is per process; changes spanning two files are two writes (see PLAN.md "Feature integration rules").
- `SECRET_KEY` falls back to a fixed dev value; set `MEDFLOW_SECRET_KEY` before any non-local use.
- Seed dates are fixed around 2026-10-20 ("this month" = October 2026 in the demo).
- Your `instance/` has your own appointments plus `expenses.json`, which your running server created from the seed when it reloaded. Run `flask --app medflow reset-demo` (it asks first) to load the full demo data.

## Failed attempts / dead ends
- Mobile overflow: `minmax(0, 1fr)` and `min-width: 0`.
- Utility-class specificity: `.page-header .page-header__jump`.
- Locking `load`/`save` separately doesn't stop lost updates; use `storage.modify`.
- A server started without `--debug` caches templates; restart it after template edits when checking in a browser.

## Failed attempts (2026-10-28)
- `load_dotenv()` with no path searches from the calling script's folder, not the working directory; fine for `scripts/`, wrong for a script elsewhere.
- `git mv medflow/static public/static` fails until `public/` exists.
