# Supabase setup (one time)

MedFlow stores each signed-in user's appointments and expenses in Supabase, protected by
Row-Level Security. These steps are done by hand in the Supabase and Google dashboards.
Nothing here deletes data. Fictional data only.

You need: the Supabase project whose URL and publishable key are in `.env`, and one or two
Google accounts to sign in with (for the isolation test, two).

## 1. Create the tables

1. Supabase dashboard → your project → **SQL Editor** → **New query**.
2. Paste all of [`schema.sql`](schema.sql) and click **Run**.
   Expected: "Success. No rows returned". If it says a table already exists, stop and ask:
   the script never drops anything.
3. Check: **Table Editor** shows `appointments` and `expenses`, each without the
   "RLS disabled" warning. **Authentication → Policies** shows 4 policies per table.

## 2. Create a Google OAuth client

1. Supabase → **Authentication → Sign In / Providers → Google**. Copy the **Callback URL**
   shown there (`https://<project-ref>.supabase.co/auth/v1/callback`). Leave the page open.
2. [Google Cloud Console](https://console.cloud.google.com/) → create or pick a project →
   **Google Auth Platform** (APIs & Services → OAuth consent screen):
   - **Branding:** app name `MedFlow AI (demo)`, your email as support and developer contact.
   - **Audience:** user type **External**, publishing status **Testing**. Under **Test users**,
     add the Google accounts that may sign in. Leave it in Testing: only listed accounts can
     use the app, which keeps it a closed demo.
   - **Data access:** the default `openid`, `email` and `profile` scopes are all MedFlow needs.
3. **Clients → Create client → Web application**, name `MedFlow Supabase`.
   - **Authorized redirect URIs:** paste the Supabase Callback URL from step 2.1.
   - Authorized JavaScript origins are not needed (sign-in is a server-side redirect).
   - Click **Create** and keep the dialog with the **Client ID** and **Client secret** open.

## 3. Turn on Google in Supabase

1. Back on Supabase → **Authentication → Sign In / Providers → Google**: enable it, paste the
   Client ID and Client secret, **Save**.
   The client secret lives only in Supabase. Don't put it in `.env`, the repo or chat.
2. **Authentication → URL Configuration:**
   - **Site URL:** `http://localhost:5000`
   - **Redirect URLs:** add both `http://localhost:5000/auth/callback` and
     `http://127.0.0.1:5000/auth/callback`. (The Vercel URL is added at deploy time.)
     A callback that isn't listed sends you to the Site URL instead and sign-in fails with
     "Sign-in didn't finish".

## 4. Optional: longer sessions for the demo

MedFlow keeps only the access token (the refresh token is discarded), so you sign in again
when it expires. The default is 1 hour. To make a demo less likely to hit it, set
**Project Settings → JWT Keys → Access token expiry** to e.g. `28800` (8 hours). Longer means
a stolen cookie works longer, so keep it short outside a demo.

## 5. Run and sign in

```
flask --app medflow run --debug
```

Open http://localhost:5000, click **Continue with Google**, and sign in with a test user.
A new account starts with the fictional demo data. `SUPABASE_URL` in `.env` should be just
`https://<project-ref>.supabase.co`; the app trims anything after it.

## 6. Check that users are isolated

1. Sign in once with each of two test accounts (sign out in between).
2. **Authentication → Users:** copy both user ids into the two `EDIT` lines of
   [`isolation_test.sql`](isolation_test.sql).
3. SQL Editor → New query → paste → **Run**. Every row should show `pass = true`.
   It runs in a transaction that is rolled back, so it changes nothing.

## Removing it later

Dropping the tables deletes everyone's data and can't be undone, so it isn't scripted here.
