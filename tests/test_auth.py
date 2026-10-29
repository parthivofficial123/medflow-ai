"""Google Sign-In, the sign-in guard, user isolation and the app's routes on the Supabase backend."""

import base64
import hashlib
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import g

from medflow import create_app, storage
from tests.conftest import SUPABASE_CONFIG, get_csrf_token, sign_in

APPOINTMENT = {
    "date": "2026-11-20", "time": "10:00", "provider": "Dr. Ada Reyes (fictional)",
    "location": "Pine Street Clinic", "reason": "Follow-up visit", "notes": "", "reminder_days_before": "",
}
EXPENSE = {
    "date": "2026-10-18", "category": "lab", "provider": "Brightpath Lab (fictional)",
    "description": "Vitamin D test", "estimated": "80", "actual": "", "paid": "", "appointment_id": "",
}


def post(client, url, data=None):
    return client.post(url, data={**(data or {}), "csrf_token": get_csrf_token(client)})


def rows(db, client, table):
    return sorted(db.user_rows(table, client.user_id), key=lambda r: r["id"])


def row(db, client, table, row_id):
    return next((r for r in rows(db, client, table) if r["id"] == row_id), None)


# Signing in

@pytest.mark.parametrize("path", ["/", "/appointments/", "/appointments/1", "/expenses/", "/bills/",
                                  "/account/reset"])
def test_private_pages_redirect_to_sign_in(sb_app, path):
    response = sb_app.test_client().get(path)
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_private_posts_redirect_to_sign_in_and_change_nothing(sb_app, fake_db):
    client = sb_app.test_client()
    response = client.post("/appointments/", data={**APPOINTMENT, "csrf_token": get_csrf_token(client, "/login")})
    assert response.headers["Location"] == "/login"
    assert fake_db.requests == []


def test_login_page_offers_google_and_hides_the_app(sb_app):
    html = sb_app.test_client().get("/login").get_data(as_text=True)
    assert "Continue with Google" in html
    assert "fictional data only" in html
    assert 'aria-label="Main"' not in html


def test_start_sends_the_user_to_supabase_with_a_pkce_challenge(sb_app):
    client = sb_app.test_client()
    response = client.post("/login", data={"csrf_token": get_csrf_token(client, "/login")})
    url = urlsplit(response.headers["Location"])
    query = parse_qs(url.query)
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://demo-ref.supabase.co/auth/v1/authorize"
    assert query["provider"] == ["google"]
    assert query["redirect_to"] == ["http://localhost/auth/callback"]
    assert query["code_challenge_method"] == ["s256"]
    with client.session_transaction() as s:
        verifier = s["pkce_verifier"]
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == [expected]
    assert verifier not in response.headers["Location"]


def test_start_needs_the_csrf_token(sb_app):
    assert sb_app.test_client().post("/login").status_code == 400


def test_sign_in_keeps_only_the_access_token_and_seeds_demo_data(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    with client.session_transaction() as s:
        assert set(s) <= {"access_token", "expires_at", "email", "csrf_token", "_flashes"}
        assert s["access_token"].startswith("token-")
        assert "refresh" not in str(dict(s))
    assert len(rows(fake_db, client, "appointments")) == 6
    assert len(rows(fake_db, client, "expenses")) == 7
    html = client.get("/appointments/").get_data(as_text=True)
    assert "a@example.test" in html and "Sign out" in html
    assert "token-" not in html


def test_sign_in_does_not_reseed_a_user_who_has_data(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    post(client, "/expenses/1/delete")
    user_id = client.user_id
    token = next(t for t, u in fake_db.tokens.items() if u == user_id)
    with client.session_transaction() as s:
        s.clear()
    client.post("/login", data={"csrf_token": get_csrf_token(client, "/login")})
    with client.session_transaction() as s:
        fake_db.codes["again"] = (s["pkce_verifier"], user_id, "a@example.test")
    client.get("/auth/callback?code=again")
    assert len(fake_db.user_rows("expenses", user_id)) == 6
    assert token in fake_db.tokens


def test_sign_in_returns_to_the_page_that_was_asked_for(sb_app, fake_db):
    client = sb_app.test_client()
    client.get("/expenses/?month=2026-10")
    user_id, _ = fake_db.add_user("a@example.test")
    client.post("/login", data={"csrf_token": get_csrf_token(client, "/login")})
    with client.session_transaction() as s:
        fake_db.codes["c"] = (s["pkce_verifier"], user_id, "a@example.test")
    response = client.get("/auth/callback?code=c")
    assert response.headers["Location"] == "/expenses/?month=2026-10"


def test_a_missing_page_does_not_replace_the_page_to_return_to(sb_app, fake_db):
    client = sb_app.test_client()
    client.get("/expenses/")
    client.get("/favicon.ico")  # browsers ask for this on the sign-in page
    with client.session_transaction() as s:
        assert s["next"] == "/expenses/"


@pytest.mark.parametrize("next_path", ["//evil.example/", "/\\evil.example", "https://evil.example/",
                                       "/\t/evil.example", "/\n/evil.example"])
def test_sign_in_never_redirects_off_site(sb_app, fake_db, next_path):
    client = sb_app.test_client()
    user_id, _ = fake_db.add_user("a@example.test")
    client.post("/login", data={"csrf_token": get_csrf_token(client, "/login")})
    with client.session_transaction() as s:
        s["next"] = next_path
        fake_db.codes["c"] = (s["pkce_verifier"], user_id, "a@example.test")
    assert client.get("/auth/callback?code=c").headers["Location"] == "/"


@pytest.mark.parametrize("query", ["", "?code=wrong", "?error=access_denied"])
def test_failed_callback_signs_nobody_in(sb_app, fake_db, query):
    client = sb_app.test_client()
    client.post("/login", data={"csrf_token": get_csrf_token(client, "/login")})
    response = client.get(f"/auth/callback{query}", follow_redirects=True)
    assert "Sign-in didn&#39;t finish" in response.get_data(as_text=True)
    with client.session_transaction() as s:
        assert "access_token" not in s


def test_callback_without_a_started_sign_in_is_refused(sb_app, fake_db):
    user_id, _ = fake_db.add_user("a@example.test")
    fake_db.codes["c"] = ("any-verifier", user_id, "a@example.test")
    client = sb_app.test_client()
    assert client.get("/auth/callback?code=c").headers["Location"] == "/login"
    with client.session_transaction() as s:
        assert "access_token" not in s


def test_expired_session_asks_to_sign_in_again(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    with client.session_transaction() as s:
        s["expires_at"] = int(time.time()) + 30
    response = client.get("/expenses/", follow_redirects=True)
    assert "Your session ended" in response.get_data(as_text=True)
    with client.session_transaction() as s:
        assert "access_token" not in s


def test_token_rejected_by_supabase_signs_the_user_out(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    fake_db.expired.update(fake_db.tokens)
    response = client.get("/expenses/")
    assert response.headers["Location"] == "/login"
    with client.session_transaction() as s:
        assert "access_token" not in s


def test_sign_out_revokes_the_session_and_clears_the_cookie(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    with client.session_transaction() as s:
        token = s["access_token"]
    response = post(client, "/logout")
    assert response.headers["Location"] == "/login"
    assert fake_db.signed_out == [(token, "local")]
    with client.session_transaction() as s:
        assert "access_token" not in s and "email" not in s


# Each user sees and changes only their own data

def test_users_never_see_each_others_data(sb_app, fake_db):
    alice = sign_in(sb_app, fake_db, "alice@example.test")
    bob = sign_in(sb_app, fake_db, "bob@example.test")
    post(alice, "/appointments/", {**APPOINTMENT, "reason": "Alice-only visit"})
    post(alice, "/expenses/", {**EXPENSE, "description": "Alice-only test"})

    assert "Alice-only" not in bob.get("/appointments/").get_data(as_text=True)
    assert "Alice-only" not in bob.get("/expenses/").get_data(as_text=True)
    assert bob.get("/appointments/7").status_code == 404
    assert post(bob, "/appointments/7/edit", {**APPOINTMENT, "reason": "Hijacked"}).status_code == 404
    assert post(bob, "/appointments/7/delete").status_code == 404
    assert post(bob, "/expenses/8/delete").status_code == 404
    assert row(fake_db, alice, "appointments", 7)["reason"] == "Alice-only visit"
    assert row(fake_db, alice, "expenses", 8)["description"] == "Alice-only test"


def test_a_user_cannot_link_an_expense_to_someone_elses_appointment(sb_app, fake_db):
    alice = sign_in(sb_app, fake_db, "alice@example.test")
    bob = sign_in(sb_app, fake_db, "bob@example.test")
    post(alice, "/appointments/", APPOINTMENT)
    response = post(bob, "/expenses/", {**EXPENSE, "appointment_id": "7"})
    assert response.status_code == 400
    assert len(rows(fake_db, bob, "expenses")) == 7


def test_same_ids_for_two_users_stay_separate(sb_app, fake_db):
    alice = sign_in(sb_app, fake_db, "alice@example.test")
    bob = sign_in(sb_app, fake_db, "bob@example.test")
    post(alice, "/appointments/1/status", {"status": "cancelled"})
    assert row(fake_db, alice, "appointments", 1)["status"] == "cancelled"
    assert row(fake_db, bob, "appointments", 1)["status"] == "scheduled"


def test_reset_replaces_only_the_signed_in_users_data(sb_app, fake_db):
    alice = sign_in(sb_app, fake_db, "alice@example.test")
    bob = sign_in(sb_app, fake_db, "bob@example.test")
    post(alice, "/appointments/", APPOINTMENT)
    post(bob, "/appointments/", APPOINTMENT)
    response = post(alice, "/account/reset", {"confirmed": "yes"})
    assert response.status_code == 302
    assert len(rows(fake_db, alice, "appointments")) == 6
    assert len(rows(fake_db, bob, "appointments")) == 7


def test_reset_needs_confirmation(sb_app, fake_db):
    alice = sign_in(sb_app, fake_db)
    post(alice, "/appointments/", APPOINTMENT)
    assert post(alice, "/account/reset").headers["Location"] == "/account/reset"
    assert len(rows(fake_db, alice, "appointments")) == 7


# The app's features on the Supabase backend

def test_appointments_and_tasks_work_on_supabase(sb_app, fake_db, data_dir):
    client = sign_in(sb_app, fake_db)
    assert post(client, "/appointments/", APPOINTMENT).status_code == 302
    post(client, "/appointments/7/tasks", {"text": "Bring insurance card (fictional)"})
    post(client, "/appointments/7/tasks/1/toggle")
    post(client, "/appointments/7/edit", {**APPOINTMENT, "reason": "Changed reason"})
    appt = row(fake_db, client, "appointments", 7)
    assert appt["reason"] == "Changed reason" and appt["updated_at"]
    assert appt["tasks"] == [{"id": 1, "text": "Bring insurance card (fictional)", "done": True}]
    assert "Changed reason" in client.get("/appointments/7").get_data(as_text=True)
    assert not data_dir.exists()


def test_modify_sends_only_the_changed_fields(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    fake_db.requests.clear()
    post(client, "/appointments/1/status", {"status": "completed"})
    assert ("appointments", "update") in fake_db.requests
    assert ("appointments", "insert") not in fake_db.requests
    assert ("appointments", "delete") not in fake_db.requests


def test_expenses_keep_unknown_and_zero_amounts_apart(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    post(client, "/expenses/", {**EXPENSE, "actual": ""})
    post(client, "/expenses/", {**EXPENSE, "estimated": "", "actual": "0"})
    assert row(fake_db, client, "expenses", 8)["actual_cents"] is None
    assert row(fake_db, client, "expenses", 9)["actual_cents"] == 0
    post(client, "/expenses/9/edit", {**EXPENSE, "estimated": "", "actual": "40", "paid": "40"})
    assert row(fake_db, client, "expenses", 9)["paid_cents"] == 4000


def test_deleting_an_appointment_keeps_its_expenses_unlinked(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    linked = [e for e in rows(fake_db, client, "expenses") if e["appointment_id"] == 5]
    assert linked
    assert post(client, "/appointments/5/delete").status_code == 302
    assert row(fake_db, client, "appointments", 5) is None
    for e in linked:
        kept = row(fake_db, client, "expenses", e["id"])
        assert kept["appointment_id"] is None and kept["appointment_label"] == e["appointment_label"]


def test_bill_charges_are_saved_to_supabase(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    form = {
        "review_id": "review-test-1", "row_count": "1", "provider": "Lakeside Imaging (fictional)", "bill_total": "$65.00",
        "bill_date": "2026-10-10", "include-0": "yes", "description-0": "Radiologist reading",
        "date-0": "2026-10-02", "amount-0": "65.00", "category-0": "imaging",
        "explanation-0": "A review.", "on_bill-0": "65.00",
    }
    assert post(client, "/bills/save", form).status_code == 302
    saved = row(fake_db, client, "expenses", 8)
    assert saved["source"] == "bill" and saved["actual_cents"] == 6500 and saved["paid_cents"] == 0


def test_database_failure_shows_an_error_and_never_falls_back_to_json(sb_app, fake_db, data_dir):
    client = sign_in(sb_app, fake_db)
    fake_db.fail_on = ("appointments", "insert")
    response = post(client, "/appointments/", APPOINTMENT)
    assert response.status_code == 503
    html = response.get_data(as_text=True)
    assert "may not have been saved" in html
    assert "fake network failure" not in html and "token-" not in html
    assert not data_dir.exists()


def test_a_row_deleted_elsewhere_during_a_change_is_an_error(sb_app, fake_db):
    sign_in(sb_app, fake_db)
    with sb_app.test_request_context():
        g.access_token = next(iter(fake_db.tokens))
        with pytest.raises(storage.DatabaseError, match="deleted elsewhere"):
            with storage.modify("appointments") as records:
                fake_db.rows["appointments"] = [r for r in fake_db.rows["appointments"] if r["id"] != 1]
                records[0]["status"] = "completed"


def test_two_records_created_at_once_cannot_share_an_id(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    with sb_app.test_request_context():
        g.access_token = next(iter(fake_db.tokens))
        with pytest.raises(storage.DatabaseError, match="23505"):
            with storage.modify("expenses") as records:
                # Another request saves id 8 between this one's load and save.
                fake_db.rows["expenses"].append({**records[0], "id": 8, "user_id": client.user_id})
                records.append({**records[0], "id": 8})


# Startup settings

def test_json_mode_needs_no_sign_in(client):
    assert client.get("/login").headers["Location"] == "/"
    html = client.get("/appointments/").get_data(as_text=True)
    assert "Sign out" not in html and "Reset my demo data" in html


@pytest.mark.parametrize("changes, message", [
    ({"STORAGE": "sqlite"}, "MEDFLOW_STORAGE"),
    ({"SUPABASE_URL": ""}, "SUPABASE_URL"),
    ({"SUPABASE_URL": "demo-ref.supabase.co"}, "SUPABASE_URL"),
    ({"SUPABASE_PUBLISHABLE_KEY": ""}, "SUPABASE_PUBLISHABLE_KEY"),
    ({"SUPABASE_PUBLISHABLE_KEY": "sb_secret_abc"}, "secret key"),
    ({"SECRET_KEY": "dev-only-not-a-secret"}, "MEDFLOW_SECRET_KEY"),
    ({"STORAGE": "json", "ON_VERCEL": True}, "Vercel"),
])
def test_unsafe_settings_stop_the_app_from_starting(fake_db, changes, message):
    with pytest.raises(RuntimeError, match=message) as e:
        create_app({**SUPABASE_CONFIG, **changes})
    assert "abc" not in str(e.value)


def test_supabase_url_is_trimmed_to_the_project_origin(fake_db):
    app = create_app({**SUPABASE_CONFIG, "SUPABASE_URL": "https://demo-ref.supabase.co/rest/v1/"})
    assert app.config["SUPABASE_URL"] == "https://demo-ref.supabase.co"


def test_settings_come_from_the_environment(fake_db, monkeypatch, data_dir):
    monkeypatch.setenv("MEDFLOW_STORAGE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://demo-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("MEDFLOW_SECRET_KEY", "env-secret")
    app = create_app({"DATA_DIR": str(data_dir)})
    assert app.config["STORAGE"] == "supabase" and app.config["SECRET_KEY"] == "env-secret"
    assert not data_dir.exists()


def test_vercel_uses_secure_cookies_and_https_callbacks(fake_db, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    app = create_app(dict(SUPABASE_CONFIG))
    assert app.config["SESSION_COOKIE_SECURE"] is True
    client = app.test_client()
    proxy = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "medflow.example"}
    html = client.get("/login", headers=proxy).get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    response = client.post("/login", data={"csrf_token": token}, headers=proxy)
    assert "redirect_to=https%3A%2F%2Fmedflow.example%2Fauth%2Fcallback" in response.headers["Location"]


# Readiness audit: headers and the example settings file

def test_pages_cannot_be_framed_or_sniffed(client):
    response = client.get("/appointments/")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"
    policy = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in policy and "frame-ancestors 'none'" in policy


def test_error_pages_and_redirects_get_the_headers_too(client, sb_app):
    missing = client.get("/no-such-page")
    assert missing.status_code == 404 and missing.headers["X-Frame-Options"] == "DENY"
    redirect = sb_app.test_client().get("/appointments/")  # signed out: sent to sign in
    assert redirect.status_code == 302 and redirect.headers["X-Frame-Options"] == "DENY"


def test_env_example_holds_placeholders_only():
    text = (Path(__file__).parent.parent / ".env.example").read_text(encoding="utf-8")
    settings = dict(line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#"))
    assert set(settings) == {"MEDFLOW_STORAGE", "MEDFLOW_SECRET_KEY", "SUPABASE_URL",
                             "SUPABASE_PUBLISHABLE_KEY", "GEMINI_API_KEY", "GEMINI_MODEL"}
    for name in ("MEDFLOW_SECRET_KEY", "SUPABASE_PUBLISHABLE_KEY", "GEMINI_API_KEY"):
        assert settings[name] == "", name
    assert "<project-ref>" in settings["SUPABASE_URL"]


def test_a_blank_secret_key_in_env_falls_back_to_the_dev_key_locally(monkeypatch, data_dir):
    # .env.example leaves MEDFLOW_SECRET_KEY blank; an empty key would break every session.
    monkeypatch.setenv("MEDFLOW_SECRET_KEY", "")
    app = create_app({"DATA_DIR": str(data_dir)})
    assert app.config["SECRET_KEY"] == "dev-only-not-a-secret"
    assert app.test_client().get("/appointments/").status_code == 200


def test_a_blank_secret_key_still_stops_supabase_mode(fake_db, monkeypatch):
    monkeypatch.setenv("MEDFLOW_SECRET_KEY", "")
    config = {k: v for k, v in SUPABASE_CONFIG.items() if k != "SECRET_KEY"}
    with pytest.raises(RuntimeError, match="MEDFLOW_SECRET_KEY"):
        create_app(config)
