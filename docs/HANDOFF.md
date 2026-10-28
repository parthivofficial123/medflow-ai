# Handoff

_Last updated: 2026-10-28. **Step 1 (Gemini + review-and-save) built and tested; the real-API benchmark is still to run.**_

## Goal
Build the MedFlow AI MVP in 8 days, following `docs/PLAN.md`. Next: approve an AI provider, wire it into `bill_ai.call_model()`, then Day 5 (B4–B6).

## Plan revision (2026-10-21)
- AI bill understanding is now the primary feature (Days 4–5), using the Anthropic `anthropic` SDK. No `python-dotenv`; set `ANTHROPIC_API_KEY` in the shell.
- MedPrice moves to Day 6 and uses a small hand-curated set of **real** published prices (`source_url`, `as_of`, `retrieved_on`, `real: true`). Patient-side data stays fictional.
- Glossary and "Report an issue" dropped. Dashboard folds into Day 7.
- Project structure unchanged. See `docs/PLAN.md` "Approved decisions" 6–7 and the bill analysis spec.

## Current state
- Committed locally, not pushed or deployed. `pytest`: 327/327 pass.
- Gemini is wired into `bill_ai.call_model()` (free tier, `gemini-3.8-flash`, stdlib `urllib`, key from `GEMINI_API_KEY` in an `x-goog-api-key` header). **Not yet called for real:** the key isn't visible to the Claude desktop app's environment. The field name `responseJsonSchema` is unverified until the first real call.
- Day 5 done: the review page is an editable form (tick, fix description/date/amount/category, provider); "Save ticked charges" validates every row with `expenses.validate` and saves them in one `storage.modify("expenses")` with `source: "bill"`. Saved rows show a "From a bill" chip.
- Browser-checked with a fake AI (scratchpad launcher, not in the repo) at 1280px and 375px: upload → fix a flagged row → save 3 → expenses list and totals updated.

## Step 1 details
- `bill_ai.py`: no automatic retries (free-tier quota). 429 → "free AI limit"; 401/403 → "key refused"; 5xx → "having problems"; timeouts (incl. connect) → 504; blocked/empty/MAX_TOKENS replies → plain messages. Logs show only the HTTP status, never the key or bill text.
- `tests/conftest.py`: every test unsets `GEMINI_API_KEY` and replaces `urllib.request.urlopen` with a function that fails the test, so no test can reach the network.
- Review form round-trips explanation, the amount and date as printed, and the AI warnings in hidden fields; `row_count` and `bill_date` coming back from the browser are re-checked.
- `scripts/benchmark_bills.py` + `data/sample_bills/expected.json`: 3 real calls, scores items/amounts/dates/totals and whether the injection bill kept its amounts.

## Day 4 features
- `medflow/bill_ai.py`: the only module that talks to an AI provider. `PROMPT` (bill text is data, not instructions; copy amounts exactly), `ANSWER_SCHEMA` (all strings), `call_model()` (provider stub), `extract()` (JSON parse → `AIError` on failure).
- `medflow/bills.py`: `/bills/` upload → file check by leading bytes + extension (PDF/PNG/JPEG) → `extract` → `check_answer` → read-only review page. Saves nothing.
- `check_answer`: rejects wrongly shaped answers; `null` optional fields mean "not shown"; amounts through `expenses.parse_money`, dates through `dates.check_date`; unreadable or negative amounts (`-$50`, `($50)`) are flagged, never guessed; items total only when every amount parsed; compares with the bill's printed total; flags an unreadable total. Text trimmed; max 100 items.
- Uploads stay in memory: `MemoryUploadRequest` in `__init__.py` overrides Werkzeug's `_get_file_stream` so no upload spills to a temp file. `MAX_CONTENT_LENGTH` = 5 MB with a friendly 413 page.
- `data/sample_bills/`: 3 fictional PDFs, including `03_prompt_injection_test.pdf` for the Day 5 security review. `.gitattributes` marks PDFs binary (line-ending conversion would corrupt them).

## Known limitations (Day 4)
- The 413 message mentions a file even on other forms (only reachable with 5 MB+ text).
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

## Next steps
1. Make `GEMINI_API_KEY` visible to the desktop app (user-level env var, restart the app), then run `python scripts/benchmark_bills.py` and record the results here.
2. If the first real call returns HTTP 400, check `generationConfig` field names against Google's API reference (`responseJsonSchema` vs `responseSchema`).
3. Step 2: Supabase storage + Google Sign-In (access token only in the cookie), per docs/PLAN.md decision 9.
