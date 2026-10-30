# Deploying MedFlow AI to Vercel

Prepared 2026-10-29. Not deployed yet: every step below waits for the owner's go-ahead.
Background and earlier findings: `docs/GITHUB_READINESS.md` section 4.

## What is already in the repository

| Item | State |
|---|---|
| Entry point | `app.py` exports `app = create_app()`; Vercel's Flask preset finds it. |
| Python | `.python-version` = 3.14, the version every test runs on (Vercel supports 3.12–3.14). |
| Dependencies | `requirements.txt`, pinned: Flask 3.1.3, supabase 2.33.0, python-dotenv 1.2.4. |
| Function duration | `vercel.json` sets `app.py` to 60 s. Bill analysis gives up after 45 s. |
| Static files | `public/static/` is served by Vercel's CDN at `/static/...`, the URLs Flask generates. |
| Excluded from the bundle | `.vercelignore`: `.env*`, `.venv/`, `instance/`, `tests/`, `scripts/`, `docs/`, `supabase/`, sample bills, `.claude/`. |
| On Vercel (`VERCEL=1`) | Supabase mode required, `Secure` session cookie, `ProxyFix` so the OAuth callback is `https://`. Refuses to start without a real secret key or with a `sb_secret_` key. |
| Storage | Nothing is written to disk in Supabase mode; uploads stay in memory (4 MB cap, under Vercel's 4.5 MB). |
| Demo safety | "Reset my demo data" is hidden and returns 404 unless `MEDFLOW_DEMO_RESET=1`. Don't set it on Vercel. |

## 1. Environment variables (Vercel → Project → Settings → Environment Variables, Production)

| Name | Value |
|---|---|
| `MEDFLOW_STORAGE` | `supabase` |
| `MEDFLOW_SECRET_KEY` | a **new** random value: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SUPABASE_URL` | your project URL, `https://<ref>.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | the **publishable** key (never `sb_secret_...`) |
| `GEMINI_API_KEY` | your Gemini key |
| `GEMINI_MODEL` | optional; leave unset for `gemini-3.5-flash-lite` |

Do not set `MEDFLOW_DEMO_RESET`. `VERCEL` is set by Vercel itself.

## 2. Supabase and Google configuration

1. Deploy once (step 3) to learn the production domain, e.g. `https://<project>.vercel.app`.
2. Supabase → Authentication → URL Configuration:
   - **Redirect URLs:** add `https://<production-domain>/auth/callback`. Keep the two localhost
     entries so local development still works.
   - **Site URL:** set to `https://<production-domain>` if the demo runs on Vercel. (It is only the
     fallback when a redirect isn't on the list; preview deployments use other hostnames and will
     fall back to it, so sign in on the production URL only.)
3. Google Cloud → OAuth client: **no change.** Its redirect URI is Supabase's
   `https://<ref>.supabase.co/auth/v1/callback`, which doesn't change. The consent screen stays in
   Testing; every presenter account must be a listed test user.
4. Optional for the demo day: Supabase → Authentication → Sessions → raise the JWT expiry above
   1 hour so a session can't end mid-presentation (`supabase/README.md` step 4).

## 3. Deployment steps

1. Push `main` to GitHub (after approval).
2. Vercel → Add New → Project → import the repository. Framework preset: **Flask** (detected).
   Root directory: the repository root. No build command.
3. Add the environment variables from section 1 (Production) **before** the first deploy, or
   redeploy after adding them. A missing one stops the app at startup with a clear log message.
4. Deploy. Note the production domain.
5. Do section 2 with that domain.
6. Run the smoke test (section 4).

## 4. Post-deployment smoke test

Use the production URL, a listed Google test user, and the existing demo account.

1. `/` shows the landing page (signed out); the browser console has no errors.
2. `https://<domain>/static/css/app.css` returns 200; the page is styled; the tab shows the icon.
3. "Continue with Google" → Google → back to `/appointments/` signed in. (If it fails with
   "Sign-in didn't finish", the callback URL in section 2 is missing.)
4. Appointments shows 1 upcoming, 4 past; Expenses shows October tiles $90.00 / $115.00 /
   $25.00 / $90.00 / $0.00 and all-time totals $210.00 / $198.50 / $108.50 / $90.00 / $25.00.
5. Open an appointment: its linked expense and follow-up task are there.
6. The footer has no "Reset my demo data" link; `/account/reset` returns 404.
7. Bills: upload `data/sample_bills/02_clinic_visit_with_lab.pdf` once (one Gemini request). The
   review page appears; **click Discard** so the demo dataset is unchanged.
8. Sign out, then sign in again.
9. Vercel → Logs: no errors, and no tokens, keys or bill contents in any log line.

## 5. Rollback

- **Bad deploy after a good one:** Vercel → Deployments → the last good deployment →
  Promote to Production (instant, no rebuild).
- **First deploy fails:** present from the local app (`flask --app medflow run --debug` with
  `.env`), which uses the same Supabase data. Nothing about deploying changes the database.
- **Code:** `git revert <commit>` locally, then push; never force-push.
- **Supabase:** if you set the Site URL to the Vercel domain, set it back to
  `http://localhost:5000` when presenting locally.

## Known limits (not blockers)

- `dates.today()` uses the server clock, which is UTC on Vercel. After 5 pm Pacific "today" is
  already tomorrow: it can move an appointment from Upcoming to Past a few hours early. The demo
  dataset has nothing on Oct 30 or 31, so the demo isn't affected.
- Sessions end when the Supabase access token expires (1 hour by default); sign in again.
- `supabase/isolation_test.sql` (two-account RLS check) hasn't been run on the real project.
  The policies were reviewed and the app's isolation is tested against a fake; running the SQL
  once is still recommended before sharing the URL widely.
