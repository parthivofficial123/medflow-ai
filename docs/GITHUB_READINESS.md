# GitHub readiness audit

_Audited 2026-10-28 against commit `07759a9` (rewritten from `efdbe12` when the commit email changed) plus the fixes listed in section 5. Nothing was pushed or
deployed. No secret values appear in this report._

## 1. Executive summary

The code is in good shape for a public repository. No credential, token or `.env` value is in
any tracked file or anywhere in the Git history (all 14 commits checked). All patient-side
data is visibly fictional. The Supabase policies are correct on review. CSRF, output escaping,
upload checks and error pages all hold up.

Three things would have embarrassed or broken a public release, and all three are now fixed:
- There was no README.
- There was no `.env.example`, and `.gitignore` would have hidden one.
- Copying such an example (with a blank `MEDFLOW_SECRET_KEY=`) broke every page with a
  server error.

Four decisions remain that only you can make, listed under 9 (Final verdict). The biggest is
that the commit metadata carries a personal Gmail address. Real cross-account isolation on
Supabase has **not** been tested yet; only the offline fake has.

**Verdict: READY WITH CONDITIONS** (see section 9).

## 2. Security findings

Severity: **BLOCKER** must be fixed before publishing, **IMPORTANT** should be fixed soon,
**OPTIONAL** can wait. "Fixed" means it was fixed in this audit, with a regression test.

### Checked and sound

| Area | Evidence |
|---|---|
| Secrets in tracked files | Every `.env` value (the Gemini key, the Supabase URL and key, the session secret) was searched for literally in the working tree and in the full history: 0 matches each. The only "hit" was `MEDFLOW_STORAGE`, whose value is the word `supabase`. Pattern scan (Google `AIza…`, `sb_secret_`, `sb_publishable_`, JWTs, `GOCSPX-`, OAuth client ids, Supabase project URLs, private keys, GitHub and OpenAI tokens, `password=`): 0 matches in history. |
| Files ever committed | 55 paths in history, no deletions; no `.env`, `instance/`, cache, venv or editor files were ever committed. |
| Supabase key type | The app only uses the publishable key and refuses to start with an `sb_secret_` key (tested). There is no service-role key anywhere. |
| RLS (`supabase/schema.sql`) | RLS is enabled on both tables, with 4 policies per table restricted to `authenticated`. `using` and `with check` both require `user_id = auth.uid()`, so a user can't read, change, delete, create or hand over another user's rows. `user_id` defaults to `auth.uid()`. `revoke all` from `anon`/`authenticated`, then only select/insert/update/delete are granted back (no truncate or references). The composite FK `(user_id, appointment_id)` makes linking an expense to another user's appointment impossible, even though FK checks bypass RLS. |
| OAuth | PKCE S256, with the verifier in the signed session cookie. That ties the code to the browser that started sign-in, which also prevents login CSRF. The session is cleared at sign-in (no fixation), and the refresh token is discarded. The post-sign-in redirect allows only same-site paths: `//`, backslashes and control characters are rejected (tested). Supabase also checks `redirect_to` against its allowlist. |
| Session cookie | Signed, HttpOnly (Flask default), SameSite=Lax, Secure on Vercel, browser-session lifetime. The server rejects tokens within 60 s of expiry. |
| CSRF | A global `before_request` check on every POST/PUT/PATCH/DELETE, with a constant-time compare. Every POST form includes the token, and tests cover missing, wrong and cross-session tokens. |
| SQL injection | No SQL is built anywhere: the PostgREST query builder is used with integer ids and constant table names (`_NAME` regex). |
| XSS | Autoescaping is on, and there is no `\|safe` or `Markup` in any template. AI text is rendered escaped and never saved (explanations aren't stored). |
| Prompt injection | The prompt says bill text is data. The JSON schema forces strings, Python parses every amount and date, and nothing is saved without review. `03_prompt_injection_test.pdf` kept its real amounts in every benchmark run. |
| Uploads | A 4 MB cap (`MAX_CONTENT_LENGTH`, friendly 413). The type comes from the file's first bytes, and the extension must agree. Uploads are kept in memory only (Werkzeug's temp-file spill is disabled, tested) and are never written or served. |
| Logs | The Gemini key goes in a header, never a URL; tests assert it never reaches logs. Auth failures log only the exception type. Config errors never include values. |
| Debug mode | `app.py` never enables debug, and the Vercel entry point can't. `--debug` appears only in local commands and in `.claude/launch.json` (localhost). |
| Personal data | Seed data, sample bills (text extracted and read) and tests use only "(fictional)" names and `example.test` emails; the PDFs have no author metadata. No machine paths or user names appear in tracked files. |

### Findings

| # | Severity | Finding | Status |
|---|---|---|---|
| S1 | IMPORTANT | **No clickjacking or content-type protection.** Any site could frame MedFlow's Delete or Save pages. | **Fixed:** every response now sends `Content-Security-Policy` (`default-src 'self'; frame-ancestors 'none'`…), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` and `Referrer-Policy: same-origin`. In the browser, the pages showed no CSP violations and the JS still works. |
| S2 | IMPORTANT (your decision) | **Every commit's author and committer is a personal Gmail address.** It becomes public on push. | Not changed: rewriting history was out of scope. Options: accept it, or rewrite the 14 commits' author to a GitHub `noreply` address before the first push (safe now, because nothing is published yet). |
| S3 | IMPORTANT | **Real cross-account isolation has not been tested.** Only `tests/fake_supabase.py` (which mimics RLS) has. | Open: run `supabase/isolation_test.sql` with two test accounts. This audit added one check to it ("A cannot hand A's rows to B"). The SQL was written by hand and has not been executed. |
| S4 | IMPORTANT | **Supabase Auth settings aren't in code.** If the Email provider or anonymous sign-ins are enabled, accounts can be created without Google. RLS still isolates them, but they could use the AI quota. | Open: in Supabase → Authentication, confirm that only Google is enabled and that anonymous sign-ins are off. |
| S5 | IMPORTANT | **Two save requests at the same instant can both save.** The "already saved" guard is a list in the cookie session, and simultaneous requests both see the old cookie. Only possible with JavaScript off (the JS guard blocks a second submit). | Open, proposed: add a `review_id` column with a unique index `(user_id, review_id)` so the database rejects the second save. This is a schema change and needs your approval. |
| S6 | OPTIONAL | No per-user rate limit on bill analysis. While the Google OAuth app is in Testing, only listed users can sign in. | Open. |
| S7 | OPTIONAL | A database error is logged with PostgREST's message, which can quote the rejected value (e.g. an invalid date). Data is fictional, and the logs stay server-side. | Open. |
| S8 | OPTIONAL | The local dev server's access log shows `/auth/callback?code=…`. The code is single-use and useless without the PKCE verifier in the cookie. | Open. |
| S9 | OPTIONAL | The session cookie is signed, not encrypted, so its owner can decode their own access token. That's by design (it's their token); HttpOnly keeps it from scripts. | Accepted. |

## 3. Functional findings

| # | Severity | Finding | Status |
|---|---|---|---|
| F1 | BLOCKER | **No README.md.** A public repo had no description, setup steps, limitations or test instructions. | **Fixed:** `README.md` covers what works and what isn't built, setup for JSON, Supabase and Gemini, tests, limitations and deployment status. |
| F2 | BLOCKER | **No `.env.example`, and `.gitignore`'s `.env.*` rule would have ignored one.** | **Fixed:** `.env.example` has placeholders only (a test enforces this), `!.env.example` is in `.gitignore`, and `git check-ignore` confirms it's trackable while `.env` and `.env.local` stay ignored. |
| F3 | BLOCKER | **A blank `MEDFLOW_SECRET_KEY=` line broke every page.** `os.environ.get(name, default)` returns `""` for a blank variable, so Flask had no secret key and every session raised a server error. Copying the example file would trigger this. | **Fixed:** blank now falls back to the dev key locally. Supabase mode still refuses to start without a real key (both cases tested). |
| F4 | IMPORTANT | **Incomplete features named in the docs.** Price search ("MedPrice") and the dashboard are planned in `docs/PLAN.md` and named in `CLAUDE.md`, but not built; `/` opens Appointments. `CLAUDE.md` lists price reference files under `data/` and a PRD `.docx` that aren't in the repo. | README states clearly what isn't built; the `CLAUDE.md` `data/` line now says price files are planned. |
| F5 | IMPORTANT | **The server's clock decides "today".** Upcoming vs. past, reminders and "this month" use the server's local date. On Vercel that's UTC, so in US evenings tomorrow's date shows. | Open, proposed: a `MEDFLOW_TIMEZONE` setting used by `dates.today()`. Note that `zoneinfo` needs the `tzdata` package on Windows, which would be a new dependency. |
| F6 | OPTIONAL | An expense's appointment label is a snapshot, so it keeps the old date or reason after the appointment is edited. | Open. |
| F7 | OPTIONAL | If the network drops after a busy-guarded submit, the button stays in "Reading your bill…" until a reload. | Open. |
| F8 | OPTIONAL | The 500 page says "check the terminal running MedFlow", which is misleading on Vercel. The "4 MB" and "45 seconds" hints are hard-coded (they match the constants today). | Open. |
| F9 | OPTIONAL | `MedFlow_Tool_Evaluation.md` (root) is internal research on coding tools taken from Instagram reels. It isn't sensitive, but it isn't product documentation either. | Your call: keep, move to `docs/`, or drop. |
| F10 | OPTIONAL | No LICENSE file: a public repo without one is "all rights reserved". | Your call. |

Test coverage is broad: 424 tests across storage (JSON and fake Supabase), auth, user
isolation (fake), appointments, expenses, the bill validator, Gemini retries and error paths,
CSRF, error pages and double-submit hooks. Not covered: the real Supabase and Gemini services,
the browser JavaScript (checked by hand), and Python versions other than 3.14.

## 4. Deployment findings (Vercel; not deployed)

| # | Severity | Finding |
|---|---|---|
| D1 | OK | `app.py` exports `app = create_app()`, which Vercel's Flask support detects. Static files are in `public/static/`, which Vercel serves at `/static/…`, the same URLs Flask generates. `data/seed/` is deployed (needed for new users); tests, scripts, docs, sample bills and `instance/` are excluded by `.vercelignore`. |
| D2 | OK | On Vercel (`VERCEL=1`), JSON mode is refused, the session cookie is Secure, and `ProxyFix` makes the OAuth callback URL `https`. In Supabase mode nothing writes to the read-only filesystem, and uploads never touch disk. |
| D3 | OK | Vercel's 4.5 MB request limit is above the app's 4 MB upload cap. |
| D4 | IMPORTANT | **Unpinned dependencies:** ranges such as `supabase>=2.33,<3` would let Vercel install a newer, untested minor version. **Fixed:** pinned to the tested versions (`Flask==3.1.3`, `supabase==2.33.0`, `python-dotenv==1.2.4`, `pytest==8.4.2`). `httpx`, `postgrest` and `supabase_auth` are imported directly but arrive through `supabase==2.33.0`. |
| D5 | IMPORTANT | **Python version:** tests ran only on Python 3.14.5, but Vercel defaults to 3.12. Nothing 3.13+-specific was found in the code, but it hasn't been run on 3.12. Before deploying, add a `.python-version` and run the suite on that version. |
| D6 | IMPORTANT | **Function duration:** a bill analysis can take up to about 45 s. Confirm the project's maximum function duration is at least 60 s (Project Settings → Functions). |
| D7 | IMPORTANT | **OAuth URLs:** add `https://<your-domain>/auth/callback` to Supabase → Authentication → URL Configuration and set the Site URL. Preview deployments have other hostnames, so sign-in there falls back to the Site URL and fails ("Sign-in didn't finish"). |
| D8 | IMPORTANT | **Environment variables in Vercel:** `MEDFLOW_STORAGE=supabase`, a new random `MEDFLOW_SECRET_KEY` (not the local one), `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `GEMINI_API_KEY`. The app refuses to start if any required one is missing or unsafe. |
| D9 | OPTIONAL | Several Vercel instances don't share the in-process lock. Supabase mode tolerates this: a lost race shows a 503 "reload and check" page rather than corrupting data. That's documented in `storage.py`. |
| D10 | OPTIONAL | Timezone: see F5. |

## 5. Fixes implemented

| Fix | Files | Regression tests |
|---|---|---|
| F1 README | `README.md` | (documentation) |
| F2 `.env.example` + ignore rules (also local DBs, `.mypy_cache`, `.ruff_cache`, swap files, `.claude/settings.local.json`) | `.env.example`, `.gitignore` | `test_env_example_holds_placeholders_only` |
| F3 blank secret key | `medflow/__init__.py` | `test_a_blank_secret_key_in_env_falls_back_to_the_dev_key_locally`, `test_a_blank_secret_key_still_stops_supabase_mode` |
| S1 security headers | `medflow/__init__.py` | `test_pages_cannot_be_framed_or_sniffed`, `test_error_pages_and_redirects_get_the_headers_too` |
| D4 pinned versions | `requirements.txt`, `requirements-dev.txt` | full suite on the pinned versions |
| S3 extra isolation check | `supabase/isolation_test.sql` | runs by hand on Supabase (not yet run) |
| F4 doc accuracy | `CLAUDE.md`, `docs/HANDOFF.md` | (documentation) |

No product features were added and the UI is unchanged.

## 6. Tests performed and results

- `pytest`: **424 passed** (419 before this audit, plus 5 new). Python 3.14.5, Windows.
- **Secret scans:** the literal search for `.env` values and the pattern scan over the full Git history and working tree, both as described in section 2.
- **Personal-data scans:** emails, phone numbers and SSN patterns; the user's name, email and machine paths in tracked files and history (found only in commit metadata, S2); text and metadata of the three sample PDFs.
- **`git status`:** clean before the audit. Nothing untracked and unignored except the new files above. `instance/`, `.env`, `.venv/`, `.vscode/`, `__pycache__/` and `.pytest_cache/` are confirmed ignored.
- **Browser** (offline JSON mode, throwaway data on port 5003, no Gemini call):
  - The appointment detail, expenses and bill upload pages load with the new headers and no console errors or CSP violations.
  - The busy guard still runs under the CSP: the button showed "Reading your bill…", was disabled, and the status text was set.
  - An empty upload returns the 400 "Choose a bill" message.
  - At 375 px the expenses page has no horizontal scroll.
- **Not run in this audit, by design:** live Gemini calls (the benchmark ran 3/3 earlier today, recorded in `HANDOFF.md`), Google Sign-In, and real Supabase. You verified those earlier: sign-in, persistence, appointment–expense linking, and Gemini extraction of a fictional bill.

## 7. Known limitations

- Fictional data only: the Gemini free tier may use inputs, and there's no compliance review.
- Sessions end when the Supabase access token expires (1 h by default); there's no refresh.
- `storage.modify` on Supabase is several requests, not a transaction. Concurrent creates can collide on an id, and the user sees a 503.
- Duplicate save under a true double POST with JavaScript off (S5). The server clock decides "today" (F5).
- Gemini free-tier capacity isn't guaranteed. The 20 s per-attempt limit was measured on small text PDFs only.
- Price search and the dashboard aren't built.

## 8. Remaining manual verification

1. Run `supabase/isolation_test.sql` with two Google test accounts; every row should say `pass = true` (S3).
2. In Supabase → Authentication: only Google enabled, anonymous sign-ins off (S4).
3. Before any deploy: `.python-version` plus the test suite on that version, function duration ≥ 60 s, callback URL and Site URL in Supabase, env vars in Vercel (D5–D8). Then run `/security-review`.
4. On Friday morning, run `python scripts/benchmark_bills.py` once.

## 9. Final verdict: **READY WITH CONDITIONS**

The repository is safe to publish: no secrets, no real patient data, and the blockers found
are fixed. Before the first push, decide:

1. **Commit email (S2):** publish the commits as they are, or first rewrite the author to a GitHub `noreply` address.
2. **LICENSE (F10):** add one, or publish as all rights reserved.
3. **`MedFlow_Tool_Evaluation.md` (F9):** keep, move, or remove.
4. **Isolation claim (S3):** until `isolation_test.sql` has passed on the real project, say "isolation enforced by RLS policies, tested against a fake" rather than "tested".

Deployment is a separate gate (section 4): it's prepared, not verified on Vercel.
