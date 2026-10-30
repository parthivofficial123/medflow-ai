import re
import threading
import urllib.request
from datetime import date

import pytest

from medflow import auth, create_app, dates, storage
from tests.fake_supabase import FakeSupabase

# Every test runs "on" this date, so upcoming/past, reminders and "this month" are stable.
TODAY = date(2026, 10, 20)


@pytest.fixture(autouse=True)
def pin_today(monkeypatch):
    monkeypatch.setattr(dates, "today", lambda: TODAY)


@pytest.fixture(autouse=True)
def no_network_or_ai_key(monkeypatch):
    # Tests never call a real AI service, even if a developer has GEMINI_API_KEY set.
    # The same for a developer's Supabase or Vercel settings: tests choose their own.
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "MEDFLOW_STORAGE", "MEDFLOW_SECRET_KEY", "SUPABASE_URL",
                 "SUPABASE_PUBLISHABLE_KEY", "VERCEL", "MEDFLOW_DEMO_RESET"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*args, **kwargs):
        raise AssertionError("A test tried to use the network.")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "instance"


@pytest.fixture
def app(data_dir):
    # Each test gets its own copy of the seed data; instance/ is never touched.
    return create_app({"TESTING": True, "SECRET_KEY": "test-secret", "DATA_DIR": str(data_dir)})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def live_app(data_dir):
    # Without TESTING, Flask uses our 500 handler instead of raising, like a real run.
    return create_app({"SECRET_KEY": "test-secret", "DATA_DIR": str(data_dir)})


SUPABASE_CONFIG = {
    "TESTING": True,
    "SECRET_KEY": "test-secret",
    "STORAGE": "supabase",
    "SUPABASE_URL": "https://demo-ref.supabase.co",
    "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
}


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeSupabase()
    monkeypatch.setattr(storage, "create_client", db.create_client)
    monkeypatch.setattr(auth, "create_client", db.create_client)
    return db


@pytest.fixture
def sb_app(fake_db, data_dir):
    # DATA_DIR is set so tests can check that Supabase mode never writes JSON files there.
    return create_app({**SUPABASE_CONFIG, "DATA_DIR": str(data_dir)})


def sign_in(app, db, email="a@example.test"):
    """A test client signed in as a new user through the real login and callback routes."""
    user_id, _ = db.add_user(email)
    client = app.test_client()
    client.post("/login", data={"csrf_token": get_csrf_token(client, "/login")})
    with client.session_transaction() as s:
        verifier = s["pkce_verifier"]
    db.codes[f"code-{user_id}"] = (verifier, user_id, email)
    client.get(f"/auth/callback?code=code-{user_id}")
    client.user_id = user_id
    return client


def get_csrf_token(client, path="/appointments/"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def run_concurrently(app, jobs):
    """Run each job(client, token) on its own thread, all starting together; return status codes."""
    barrier = threading.Barrier(len(jobs))
    statuses = []

    def worker(job):
        client = app.test_client()
        token = get_csrf_token(client)
        barrier.wait()
        statuses.append(job(client, token).status_code)

    threads = [threading.Thread(target=worker, args=(job,)) for job in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return statuses
