import json

import pytest

from medflow import create_app
from tests.conftest import get_csrf_token

VALID = {
    "date": "2026-11-20",
    "time": "15:45",
    "reason": "Dermatology check",
    "provider": "Dr. Test Person (fictional)",
    "location": "Pinecrest Skin Clinic",
    "notes": "Ask about sunscreen.",
}


def stored(data_dir):
    return json.loads((data_dir / "appointments.json").read_text(encoding="utf-8"))


def post(client, data, token="fetch"):
    form = dict(data)
    if token == "fetch":
        form["csrf_token"] = get_csrf_token(client)
    elif token is not None:
        form["csrf_token"] = token
    return client.post("/appointments/", data=form)


# S1
def test_home_redirects_to_appointments(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/appointments/")


# S2
def test_list_shows_seeded_appointments_sorted_by_date_then_time(client):
    response = client.get("/appointments/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    order = ["Annual physical", "Fasting blood work", "Knee MRI", "Follow-up on knee MRI results"]
    positions = [html.index(reason) for reason in order]
    assert positions == sorted(positions)
    assert "Wed, Nov 4, 2026 · 8:00 AM" in html


# S3
def test_valid_submission_saves_redirects_and_persists_after_restart(client, data_dir):
    before = len(stored(data_dir))
    response = post(client, VALID)
    assert response.status_code == 302

    page = client.get("/appointments/").get_data(as_text=True)
    assert "Added: Dermatology check with Dr. Test Person (fictional)." in page
    assert "Pinecrest Skin Clinic" in page

    saved = stored(data_dir)
    assert len(saved) == before + 1
    new = saved[-1]
    assert new["id"] == max(a["id"] for a in saved[:-1]) + 1
    assert new["status"] == "scheduled"
    assert {k: new[k] for k in VALID} == VALID

    restarted = create_app({"TESTING": True, "SECRET_KEY": "test-secret", "DATA_DIR": str(data_dir)})
    assert "Dermatology check" in restarted.test_client().get("/appointments/").get_data(as_text=True)


def test_values_are_trimmed(client, data_dir):
    post(client, {**VALID, "reason": "  Eye exam  "})
    assert stored(data_dir)[-1]["reason"] == "Eye exam"


# S4
def test_missing_date_and_reason_shows_errors_keeps_input_and_writes_nothing(client, data_dir):
    before = stored(data_dir)
    response = post(client, {**VALID, "date": "", "reason": ""})
    html = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "Date is required." in html
    assert "Reason for visit is required." in html
    assert 'value="Dr. Test Person (fictional)"' in html
    assert 'value="15:45"' in html
    assert ">Ask about sunscreen.</textarea>" in html
    assert 'aria-invalid="true"' in html
    assert stored(data_dir) == before


@pytest.mark.parametrize("field, value, message", [
    ("date", "2026-13-40", "Enter a valid date"),
    ("date", "20261120", "Enter a valid date"),
    ("date", "1890-01-01", "between 2000 and 2100"),
    ("time", "25:00", "Enter a valid time"),
    ("provider", "   ", "Provider is required."),
    ("reason", "x" * 121, "120 characters or fewer"),
    ("notes", "x" * 1001, "1000 characters or fewer"),
])
def test_invalid_values_are_rejected(client, data_dir, field, value, message):
    before = stored(data_dir)
    response = post(client, {**VALID, field: value})
    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    assert stored(data_dir) == before


def test_user_text_is_escaped(client):
    post(client, {**VALID, "reason": "<script>alert(1)</script>"})
    html = client.get("/appointments/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# S5: CSRF
def test_missing_csrf_token_is_rejected(client, data_dir):
    before = stored(data_dir)
    response = post(client, VALID, token=None)
    assert response.status_code == 400
    assert "This form expired" in response.get_data(as_text=True)
    assert stored(data_dir) == before


@pytest.mark.parametrize("bad_token", ["", "wrong-token", "x" * 43])
def test_invalid_csrf_token_is_rejected(client, data_dir, bad_token):
    get_csrf_token(client)  # the session now holds a real token
    before = stored(data_dir)
    assert post(client, VALID, token=bad_token).status_code == 400
    assert stored(data_dir) == before


def test_token_from_another_session_is_rejected(app, data_dir):
    stolen = get_csrf_token(app.test_client())
    victim = app.test_client()
    get_csrf_token(victim)
    before = stored(data_dir)
    assert post(victim, VALID, token=stolen).status_code == 400
    assert stored(data_dir) == before


def test_token_without_any_session_is_rejected(app, data_dir):
    token = get_csrf_token(app.test_client())
    fresh = app.test_client()  # never loaded a page, so has no session token
    assert post(fresh, VALID, token=token).status_code == 400


def test_csrf_header_is_accepted_for_scripts(client, data_dir):
    token = get_csrf_token(client)
    response = client.post("/appointments/", data=VALID, headers={"X-CSRFToken": token})
    assert response.status_code == 302


def test_token_is_stable_within_a_session(client):
    assert get_csrf_token(client) == get_csrf_token(client)


def test_unknown_page_is_a_friendly_404(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert "Back to MedFlow" in response.get_data(as_text=True)
