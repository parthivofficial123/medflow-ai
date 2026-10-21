import json
import threading
from datetime import date

import pytest

from medflow import appointments, create_app
from tests.conftest import get_csrf_token

TODAY = date(2026, 10, 20)


@pytest.fixture(autouse=True)
def pin_today(monkeypatch):
    monkeypatch.setattr(appointments, "today", lambda: TODAY)

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


def post(client, data, token="fetch", url="/appointments/"):
    form = dict(data)
    if token == "fetch":
        form["csrf_token"] = get_csrf_token(client)
    elif token is not None:
        form["csrf_token"] = token
    return client.post(url, data=form)


def appt(data_dir, appt_id):
    return next(a for a in stored(data_dir) if a["id"] == appt_id)


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


def test_new_appointment_has_reminder_and_empty_task_list(client, data_dir):
    post(client, {**VALID, "reminder_days_before": "2"})
    new = stored(data_dir)[-1]
    assert new["reminder_days_before"] == 2
    assert new["reminder_dismissed"] is False
    assert new["tasks"] == []


def test_invalid_reminder_choice_is_rejected(client, data_dir):
    before = stored(data_dir)
    response = post(client, {**VALID, "reminder_days_before": "99"})
    assert response.status_code == 400
    assert "Choose a reminder from the list." in response.get_data(as_text=True)
    assert stored(data_dir) == before


# A1: detail, edit, delete
def test_detail_page_shows_appointment(client):
    html = client.get("/appointments/2").get_data(as_text=True)
    assert "Knee MRI" in html
    assert "Lakeside Imaging Center" in html
    assert "Bring referral letter" in html


@pytest.mark.parametrize("path", ["/appointments/999", "/appointments/999/edit", "/appointments/999/delete"])
def test_unknown_appointment_is_404(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", [
    "/appointments/999/edit", "/appointments/999/delete", "/appointments/999/status",
    "/appointments/999/tasks", "/appointments/999/reminder/dismiss",
    "/appointments/1/tasks/999/toggle", "/appointments/1/tasks/999/delete",
])
def test_posts_to_unknown_ids_are_404(client, path):
    assert post(client, {**VALID, "status": "completed", "text": "x"}, url=path).status_code == 404


def test_edit_form_is_prefilled(client):
    html = client.get("/appointments/2/edit").get_data(as_text=True)
    assert 'value="Knee MRI"' in html
    assert 'value="2026-11-04"' in html
    assert '<option value="2" selected>' in html
    assert ">No metal jewelry. Arrive 15 minutes early.</textarea>" in html


def test_edit_saves_changes_and_keeps_tasks_and_status(client, data_dir):
    before = appt(data_dir, 2)
    response = post(client, {**VALID, "reason": "Knee MRI with contrast"}, url="/appointments/2/edit")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/appointments/2")

    after = appt(data_dir, 2)
    assert after["reason"] == "Knee MRI with contrast"
    assert after["tasks"] == before["tasks"]
    assert after["status"] == before["status"]
    assert after["created_at"] == before["created_at"]
    assert "updated_at" in after
    assert "Changes saved." in client.get("/appointments/2").get_data(as_text=True)


def test_invalid_edit_shows_errors_keeps_input_and_writes_nothing(client, data_dir):
    before = stored(data_dir)
    form = {**VALID, "date": "", "provider": "Dr. Kept Value (fictional)"}
    response = post(client, form, url="/appointments/2/edit")
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Date is required." in html
    assert 'value="Dr. Kept Value (fictional)"' in html
    assert stored(data_dir) == before


def test_delete_asks_for_confirmation_first(client, data_dir):
    html = client.get("/appointments/2/delete").get_data(as_text=True)
    assert "Delete this appointment?" in html
    assert "2 follow-up tasks will be deleted too" in html
    assert len(stored(data_dir)) == 6


def test_delete_removes_appointment(client, data_dir):
    response = post(client, {}, url="/appointments/2/delete")
    assert response.status_code == 302
    assert [a["id"] for a in stored(data_dir)] == [1, 3, 4, 5, 6]
    assert "Deleted: Knee MRI" in client.get("/appointments/").get_data(as_text=True)


def test_delete_without_csrf_is_rejected(client, data_dir):
    assert post(client, {}, token=None, url="/appointments/2/delete").status_code == 400
    assert len(stored(data_dir)) == 6


# A2: upcoming / past, status
def test_upcoming_and_past_are_listed_separately(client):
    html = client.get("/appointments/").get_data(as_text=True)
    upcoming, past = html.split('id="past-heading"')
    assert "Annual physical" in upcoming and "Follow-up on knee MRI results" in upcoming
    assert "Flu shot" in past and "Dental cleaning" in past
    assert "Flu shot" not in upcoming
    assert past.index("Dental cleaning") < past.index("Flu shot")  # newest first


def test_today_counts_as_upcoming(client):
    post(client, {**VALID, "date": TODAY.isoformat(), "reason": "Same-day visit"})
    upcoming = client.get("/appointments/").get_data(as_text=True).split('id="past-heading"')[0]
    assert "Same-day visit" in upcoming


def test_cancelled_appointment_is_marked(client):
    html = client.get("/appointments/").get_data(as_text=True)
    assert "appt--cancelled" in html
    assert 'pill--cancelled">Cancelled' in html


@pytest.mark.parametrize("status", ["completed", "cancelled", "scheduled"])
def test_status_can_be_changed(client, data_dir, status):
    response = post(client, {"status": status}, url="/appointments/1/status")
    assert response.status_code == 302
    assert appt(data_dir, 1)["status"] == status


def test_unknown_status_is_rejected(client, data_dir):
    assert post(client, {"status": "deleted"}, url="/appointments/1/status").status_code == 400
    assert appt(data_dir, 1)["status"] == "scheduled"


# A3: follow-up tasks
def test_add_task(client, data_dir):
    response = post(client, {"text": "  Pick up prescription  "}, url="/appointments/3/tasks")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/appointments/3#tasks")
    assert appt(data_dir, 3)["tasks"] == [{"id": 1, "text": "Pick up prescription", "done": False}]


@pytest.mark.parametrize("text, message", [("", "Enter a follow-up task."), ("x" * 201, "200 characters or fewer")])
def test_invalid_task_is_rejected_and_input_kept(client, data_dir, text, message):
    before = stored(data_dir)
    response = post(client, {"text": text}, url="/appointments/3/tasks")
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert message in html
    assert f'value="{text}"' in html
    assert stored(data_dir) == before


def test_toggle_task_checks_and_unchecks(client, data_dir):
    post(client, {}, url="/appointments/2/tasks/1/toggle")
    assert appt(data_dir, 2)["tasks"][0]["done"] is True
    post(client, {}, url="/appointments/2/tasks/1/toggle")
    assert appt(data_dir, 2)["tasks"][0]["done"] is False


def test_delete_task(client, data_dir):
    post(client, {}, url="/appointments/2/tasks/1/delete")
    assert [t["id"] for t in appt(data_dir, 2)["tasks"]] == [2]


def test_task_ids_stay_unique_after_delete(client, data_dir):
    post(client, {}, url="/appointments/2/tasks/1/delete")
    post(client, {"text": "New task"}, url="/appointments/2/tasks")
    assert [t["id"] for t in appt(data_dir, 2)["tasks"]] == [2, 3]


def test_task_toggle_without_csrf_is_rejected(client, data_dir):
    assert post(client, {}, token=None, url="/appointments/2/tasks/1/toggle").status_code == 400
    assert appt(data_dir, 2)["tasks"][0]["done"] is False


# A4: reminders
def reminder(days, status="scheduled", dismissed=False):
    return {"date": "2026-10-23", "reminder_days_before": days, "status": status, "reminder_dismissed": dismissed}


@pytest.mark.parametrize("record, on, expected", [
    (reminder(3), date(2026, 10, 19), False),  # 4 days before: not yet
    (reminder(3), date(2026, 10, 20), True),   # exactly N days before
    (reminder(3), date(2026, 10, 23), True),   # visit day
    (reminder(3), date(2026, 10, 24), False),  # visit passed
    (reminder(0), date(2026, 10, 23), True),   # "on the day"
    (reminder(0), date(2026, 10, 22), False),
    (reminder(None), date(2026, 10, 23), False),
    (reminder(3, dismissed=True), date(2026, 10, 21), False),
    (reminder(3, status="cancelled"), date(2026, 10, 21), False),
    (reminder(3, status="completed"), date(2026, 10, 21), False),
    ({"date": "2026-10-23", "status": "scheduled"}, date(2026, 10, 23), False),  # Day 1 record
])
def test_reminder_due(record, on, expected):
    assert appointments.reminder_due(record, on) is expected


def test_due_reminder_shows_on_list(client):
    html = client.get("/appointments/").get_data(as_text=True)
    panel = html.split('class="reminders"')[1].split("</section>")[0]
    assert "Annual physical" in panel
    assert "in 3 days" in panel
    assert "Knee MRI" not in panel  # its 2-day reminder starts Nov 2


def test_dismiss_hides_reminder(client, data_dir):
    response = post(client, {"next": "list"}, url="/appointments/1/reminder/dismiss")
    assert response.headers["Location"].endswith("/appointments/")
    assert appt(data_dir, 1)["reminder_dismissed"] is True
    assert 'class="reminders"' not in client.get("/appointments/").get_data(as_text=True)


def test_dismiss_ignores_unknown_next_target(client):
    response = post(client, {"next": "https://evil.example"}, url="/appointments/1/reminder/dismiss")
    assert response.headers["Location"].endswith("/appointments/1")


def edit_form(record, **changes):
    fields = {k: record[k] for k in ("date", "time", "reason", "provider", "location", "notes")}
    return {**fields, "reminder_days_before": str(record["reminder_days_before"]), **changes}


def test_changing_date_turns_dismissed_reminder_back_on(client, data_dir):
    post(client, {}, url="/appointments/1/reminder/dismiss")
    post(client, edit_form(appt(data_dir, 1), date="2026-10-22"), url="/appointments/1/edit")
    assert appt(data_dir, 1)["reminder_dismissed"] is False


def test_editing_other_fields_keeps_reminder_dismissed(client, data_dir):
    post(client, {}, url="/appointments/1/reminder/dismiss")
    post(client, edit_form(appt(data_dir, 1), reason="Annual physical exam"), url="/appointments/1/edit")
    assert appt(data_dir, 1)["reminder_dismissed"] is True


def test_day_one_records_without_new_fields_still_work(client, data_dir):
    (data_dir / "appointments.json").write_text(json.dumps([{
        "id": 1, "date": "2026-11-01", "time": "09:00", "provider": "Dr. Old (fictional)",
        "location": "", "reason": "Old record", "notes": "", "status": "scheduled",
    }]), encoding="utf-8")
    assert client.get("/appointments/").status_code == 200
    assert client.get("/appointments/1").status_code == 200
    assert client.get("/appointments/1/edit").status_code == 200
    assert post(client, {"text": "First task"}, url="/appointments/1/tasks").status_code == 302


# A5: reset-demo
def test_reset_demo_command_restores_seed(app, data_dir):
    (data_dir / "appointments.json").write_text("[]", encoding="utf-8")
    result = app.test_cli_runner().invoke(args=["reset-demo", "--yes"])
    assert result.exit_code == 0
    assert "Demo data restored" in result.output
    assert len(stored(data_dir)) == 6


def test_reset_demo_warns_and_does_nothing_unless_confirmed(app, data_dir):
    (data_dir / "appointments.json").write_text("[]", encoding="utf-8")
    result = app.test_cli_runner().invoke(args=["reset-demo"], input="n\n")
    assert result.exit_code != 0
    assert "REPLACES all MedFlow data" in result.output
    assert stored(data_dir) == []


# Audit fix: concurrent requests
def run_concurrently(app, jobs):
    """Run each job(client) on its own thread, all starting together; return status codes."""
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


def test_20_concurrent_task_adds_all_persist(app, data_dir):
    jobs = [
        lambda c, t, i=i: c.post("/appointments/3/tasks", data={"text": f"Task {i}", "csrf_token": t})
        for i in range(20)
    ]
    assert run_concurrently(app, jobs) == [302] * 20
    tasks = appt(data_dir, 3)["tasks"]
    assert sorted(t["text"] for t in tasks) == sorted(f"Task {i}" for i in range(20))
    assert len({t["id"] for t in tasks}) == 20


def test_concurrent_reads_and_writes_all_succeed(app, data_dir):
    writes = [
        lambda c, t, i=i: c.post("/appointments/", data={**VALID, "reason": f"Visit {i}", "csrf_token": t})
        for i in range(10)
    ]
    reads = [lambda c, t: c.get("/appointments/") for _ in range(10)]
    statuses = run_concurrently(app, writes + reads)
    assert sorted(statuses) == [200] * 10 + [302] * 10
    assert len(stored(data_dir)) == 6 + 10


# Audit fix: canonical dates and times
@pytest.mark.parametrize("typed, saved", [
    ({"date": "2026-1-5"}, {"date": "2026-01-05"}),
    ({"date": " 2026-11-04 "}, {"date": "2026-11-04"}),
    ({"time": "9:5"}, {"time": "09:05"}),
    ({"time": "07:30"}, {"time": "07:30"}),
])
def test_nonstandard_dates_and_times_are_saved_in_canonical_form(client, data_dir, typed, saved):
    assert post(client, {**VALID, **typed}).status_code == 302
    new = stored(data_dir)[-1]
    assert {k: new[k] for k in saved} == saved


@pytest.mark.parametrize("field, value", [
    ("date", "2026/01/05"), ("date", "01-05-2026"), ("date", "2026-02-30"), ("date", "2026-01-05T10:00"),
    ("date", "tomorrow"), ("time", "12:60"), ("time", "24:00"), ("time", "9am"), ("time", "09:05:00"),
    ("time", "-1:00"),
])
def test_malformed_dates_and_times_are_rejected(client, data_dir, field, value):
    before = stored(data_dir)
    assert post(client, {**VALID, field: value}).status_code == 400
    assert stored(data_dir) == before


def test_nonstandard_date_with_reminder_renders_everywhere(client, data_dir):
    post(client, {**VALID, "date": "2026-10-2", "reminder_days_before": "1"})
    new = stored(data_dir)[-1]
    assert new["date"] == "2026-10-02"
    assert client.get(f"/appointments/{new['id']}").status_code == 200
    past = client.get("/appointments/").get_data(as_text=True).split('id="past-heading"')[1]
    assert "Dermatology check" in past  # Oct 2 is before the pinned Oct 20


def test_edit_also_saves_canonical_date(client, data_dir):
    post(client, edit_form(appt(data_dir, 1), date="2026-12-1"), url="/appointments/1/edit")
    assert appt(data_dir, 1)["date"] == "2026-12-01"


# Audit fix: friendly error pages
@pytest.fixture
def live_app(data_dir):
    # Without TESTING, Flask uses our 500 handler instead of raising, like a real run.
    return create_app({"SECRET_KEY": "test-secret", "DATA_DIR": str(data_dir)})


def test_corrupt_file_shows_friendly_page_with_reset_advice(live_app, data_dir):
    (data_dir / "appointments.json").write_text("[{broken", encoding="utf-8")
    response = live_app.test_client().get("/appointments/")
    html = response.get_data(as_text=True)
    assert response.status_code == 500
    assert "appointments data file is damaged" in html
    assert "reset-demo" in html
    assert "This replaces any changes you made" in html
    assert "JSONDecodeError" not in html and "Traceback" not in html and str(data_dir) not in html


def test_other_errors_show_generic_page_without_reset_advice(live_app, data_dir):
    # Valid JSON, but a record is missing fields: not corruption, so no reset advice.
    (data_dir / "appointments.json").write_text(json.dumps([{"id": 1, "date": "2026-11-01"}]), encoding="utf-8")
    response = live_app.test_client().get("/appointments/")
    html = response.get_data(as_text=True)
    assert response.status_code == 500
    assert "Something went wrong on our side" in html
    assert "reset-demo" not in html
    assert "KeyError" not in html and "Traceback" not in html


def test_wrong_method_shows_friendly_page(client):
    response = client.put("/appointments/", data={"csrf_token": get_csrf_token(client)})
    assert response.status_code == 405
    assert "Back to MedFlow" in response.get_data(as_text=True)
