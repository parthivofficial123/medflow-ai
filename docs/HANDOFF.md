# Handoff

_Last updated: 2026-10-21. **Day 3 complete. Plan revised and approved (2026-10-21); Day 4 is now bill analysis.**_

## Goal
Build the MedFlow AI MVP in 8 days, following `docs/PLAN.md`. Next: Day 4 (bill analysis, part 1, B1–B3).

## Plan revision (2026-10-21)
- AI bill understanding is now the primary feature (Days 4–5), using the Anthropic `anthropic` SDK. No `python-dotenv`; set `ANTHROPIC_API_KEY` in the shell.
- MedPrice moves to Day 6 and uses a small hand-curated set of **real** published prices (`source_url`, `as_of`, `retrieved_on`, `real: true`). Patient-side data stays fictional.
- Glossary and "Report an issue" dropped. Dashboard folds into Day 7.
- Project structure unchanged. See `docs/PLAN.md` "Approved decisions" 6–7 and the bill analysis spec.

## Current state
- Days 1–3 and the audit fixes are committed locally. Nothing is pushed.
- `pytest`: 210/210 pass (86 appointments, 22 audit, 100 expenses, plus storage).
- Checked in the browser at 1280px and 375px: expense list and summary, edit, delete confirmation, add-from-appointment prefill, appointment page with linked expenses, appointment delete confirmation. No page-level horizontal scroll (the category table scrolls inside its own box); all controls ≥ 44px.

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

## Next steps: Day 4
Follow "Bill analysis specification (Days 4–5)" in `docs/PLAN.md`:
1. Add `anthropic` to `requirements.txt` and install it.
2. Write 2–3 fictional sample bills in `data/sample_bills/`.
3. Tests first (`tests/test_bills.py`, AI faked): upload checks, response shape checks, per-item `parse_money`, flagged items, error cases.
4. `medflow/bills.py` + `templates/bills/`: upload form, AI call, read-only review page; nav link.
5. Browser check at 375px and 1280px (with a real key, sample bills only); `pytest`; `/code-review`; commit.
