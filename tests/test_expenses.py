import json

import pytest
from markupsafe import escape

from medflow import create_app, expenses, money
from tests.conftest import get_csrf_token, run_concurrently

VALID = {
    "date": "2026-10-18",
    "category": "lab",
    "provider": "Brightpath Lab (fictional)",
    "description": "Vitamin D test",
    "estimated": "80",
    "actual": "",
    "paid": "",
    "appointment_id": "",
}


def stored(data_dir, name="expenses"):
    return json.loads((data_dir / f"{name}.json").read_text(encoding="utf-8"))


def expense(data_dir, expense_id):
    return next(e for e in stored(data_dir) if e["id"] == expense_id)


def post(client, data, url="/expenses/", token="fetch"):
    form = dict(data)
    if token == "fetch":
        form["csrf_token"] = get_csrf_token(client, "/expenses/")
    return client.post(url, data=form)


# Money parsing (E1, E2)
@pytest.mark.parametrize("raw, cents", [
    ("120", 12000), ("120.5", 12050), ("120.50", 12050), ("0", 0), ("0.00", 0), (" 7 ", 700),
    ("0.29", 29), ("19.99", 1999), ("1.10", 110), ("$1,234.56", 123456), ("$ 45", 4500),
    ("1,000,000", 100_000_000), ("1.230", 123), ("", None), ("   ", None),
])
def test_parse_money_valid(raw, cents):
    assert expenses.parse_money(raw) == (cents, None)


@pytest.mark.parametrize("raw, message", [
    ("-5", "can't be negative"), ("-0.01", "can't be negative"),
    ("12.345", "at most 2 decimal places"), ("0.001", "at most 2 decimal places"),
    ("abc", "Enter an amount"), ("NaN", "Enter an amount"), ("Infinity", "Enter an amount"),
    ("1e3", "Enter an amount"), ("1,23", "Enter an amount"), ("12,34.00", "Enter an amount"),
    ("1.2.3", "Enter an amount"), ("$", None), (".5", "Enter an amount"), ("5.", "Enter an amount"),
    ("1000000.01", "$1,000,000 or less"), ("٣", "Enter an amount"),
])
def test_parse_money_invalid(raw, message):
    cents, error = expenses.parse_money(raw)
    assert cents is None
    if message is None:
        assert error is None  # "$" alone is blank
    else:
        assert message in error


@pytest.mark.parametrize("cents, text", [
    (0, "$0.00"), (5, "$0.05"), (1999, "$19.99"), (123456, "$1,234.56"), (100_000_000, "$1,000,000.00"),
    (-3650, "-$36.50"), (None, "—"),
])
def test_money_filter(cents, text):
    assert money(cents) == text


def test_money_filter_signed():
    assert money(1550, signed=True) == "+$15.50"
    assert money(0, signed=True) == "$0.00"


@pytest.mark.parametrize("cents, text", [(None, ""), (0, "0.00"), (5, "0.05"), (123456, "1234.56")])
def test_cents_to_input_round_trips(cents, text):
    assert expenses.cents_to_input(cents) == text
    if cents is not None:
        assert expenses.parse_money(text) == (cents, None)


# Derived status (E3)
@pytest.mark.parametrize("record, expected", [
    ({"actual_cents": None, "paid_cents": 0}, "not_billed"),
    ({"actual_cents": None, "paid_cents": 5000}, "not_billed"),  # deposit before the bill
    ({"actual_cents": 0, "paid_cents": 0}, "paid"),              # $0 bill: nothing owed
    ({"actual_cents": 1000, "paid_cents": 0}, "unpaid"),
    ({"actual_cents": 1000, "paid_cents": 400}, "partly_paid"),
    ({"actual_cents": 1000, "paid_cents": 1000}, "paid"),
])
def test_status(record, expected):
    assert expenses.status(record) == expected


# Summary definitions (E4), hand-computed
def e(estimated=None, actual=None, paid=0, category="visit", date="2026-10-01"):
    return {"estimated_cents": estimated, "actual_cents": actual, "paid_cents": paid, "category": category, "date": date}


def test_summary_keeps_every_total_separate():
    t = expenses.summarize([
        e(estimated=10000, actual=None, paid=0),      # pending estimate only
        e(estimated=5000, actual=6000, paid=2000),    # over estimate, partly paid
        e(estimated=None, actual=3000, paid=3000),    # bill with no estimate, paid
        e(estimated=2500, actual=0, paid=0),          # $0 bill
        e(estimated=None, actual=None, paid=0),       # nothing (not allowed by the form, but tolerated)
        e(estimated=4000, actual=None, paid=1000),    # deposit before the bill
    ])
    assert t == {
        "estimated": 10000 + 5000 + 2500 + 4000,
        "billed": 6000 + 3000 + 0,
        "billed_count": 3,                           # the $0 bill counts; unknown ones don't
        "paid": 2000 + 3000 + 1000,
        "unpaid_billed": 4000,                       # only the 6000 bill minus 2000 paid
        "pending_estimates": 10000 + 4000,
        "compared_count": 2,
        "compared_estimated": 5000 + 2500,
        "compared_actual": 6000 + 0,
    }


def test_estimates_never_count_as_unpaid_bills():
    t = expenses.summarize([e(estimated=99999, actual=None)])
    assert t["unpaid_billed"] == 0
    assert t["pending_estimates"] == 99999


def test_payment_on_unknown_bill_does_not_reduce_other_unpaid_bills():
    t = expenses.summarize([e(actual=None, paid=5000), e(actual=3000, paid=0)])
    assert t["unpaid_billed"] == 3000


def test_summary_of_nothing_is_all_zero():
    assert set(expenses.summarize([]).values()) == {0}


def test_seed_month_and_all_time_totals(app):
    # Hand-computed from data/seed/expenses.json with today pinned to 2026-10-20.
    with app.test_request_context():
        view = expenses.summary_view(json.load(open(app.config["SEED_DIR"] + "/expenses.json", encoding="utf-8")))
    assert view["month_label"] == "October 2026"
    assert view["month"] == {
        "estimated": 31000, "billed": 25249, "billed_count": 3, "paid": 6899, "unpaid_billed": 18350,
        "pending_estimates": 4000, "compared_count": 2, "compared_estimated": 27000, "compared_actual": 23350,
    }
    assert view["all"] == {
        "estimated": 78500, "billed": 27749, "billed_count": 5, "paid": 16899, "unpaid_billed": 20850,
        "pending_estimates": 49000, "compared_count": 3, "compared_estimated": 29500, "compared_actual": 23350,
    }
    assert view["by_category"]["visit"]["unpaid_billed"] == 9800
    assert view["by_category"]["imaging"]["billed_count"] == 0  # shown as "—", not $0.00
    assert "vision" not in view["by_category"]


def test_category_with_no_bills_shows_dash_not_zero(client):
    html = client.get("/expenses/").get_data(as_text=True)
    imaging_row = html.split('<th scope="row">Imaging</th>')[1].split("</tr>")[0]
    cells = [c.split("</td>")[0] for c in imaging_row.split("<td>")[1:]]
    assert cells == ["$450.00", "—", "$100.00", "$0.00", "$450.00"]


def test_list_page_shows_month_summary_and_labels(client):
    html = client.get("/expenses/").get_data(as_text=True)
    assert "October 2026" in html
    assert "Unpaid recorded bills" in html
    assert "$183.50" in html            # month unpaid recorded bills
    assert "Expected, not billed yet" in html
    assert "You owe" not in html
    assert "-$36.50" in html            # billed vs estimate for the month
    assert "Not billed yet" in html


# CRUD and validation (E1)
def test_create_stores_cents_and_defaults(client, data_dir):
    response = post(client, {**VALID, "estimated": "$1,234.5"})
    assert response.status_code == 302
    new = stored(data_dir)[-1]
    assert new["estimated_cents"] == 123450
    assert new["actual_cents"] is None
    assert new["paid_cents"] == 0
    assert new["appointment_id"] is None


def test_blank_actual_is_unknown_and_zero_actual_is_zero(client, data_dir):
    post(client, {**VALID, "actual": ""})
    post(client, {**VALID, "actual": "0"})
    unknown, zero = stored(data_dir)[-2:]
    assert unknown["actual_cents"] is None
    assert zero["actual_cents"] == 0
    assert expenses.status(unknown) == "not_billed"
    assert expenses.status(zero) == "paid"


@pytest.mark.parametrize("changes, field_error", [
    ({"estimated": "", "actual": ""}, "Enter an estimated amount, a billed amount, or both."),
    ({"estimated": "-5"}, "can't be negative"),
    ({"actual": "12.345"}, "at most 2 decimal places"),
    ({"actual": "50", "paid": "60"}, "Paid can't be more than the billed amount."),
    ({"paid": "abc"}, "Enter an amount"),
    ({"category": "spa"}, "Choose a category from the list."),
    ({"category": ""}, "Choose a category from the list."),
    ({"date": "2026-02-30"}, "Enter a valid date"),
    ({"date": ""}, "Date of service is required."),
    ({"provider": " "}, "Provider is required."),
    ({"description": "x" * 201}, "200 characters or fewer"),
    ({"appointment_id": "999"}, "Choose an appointment from the list."),
    ({"appointment_id": "abc"}, "Choose an appointment from the list."),
])
def test_invalid_input_is_rejected_and_kept(client, data_dir, changes, field_error):
    before = stored(data_dir)
    response = post(client, {**VALID, **changes})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert escape(field_error) in html
    kept = "description" if "provider" in changes else "provider"
    assert f'value="{VALID[kept]}"' in html  # a field the user didn't break is redisplayed
    assert stored(data_dir) == before


def test_typed_amount_is_redisplayed_exactly(client):
    html = post(client, {**VALID, "estimated": "12.345"}).get_data(as_text=True)
    assert 'value="12.345"' in html


def test_paid_before_bill_is_allowed(client, data_dir):
    assert post(client, {**VALID, "estimated": "300", "paid": "100"}).status_code == 302
    assert stored(data_dir)[-1]["paid_cents"] == 10000


def test_edit_form_is_prefilled_with_dollar_amounts(client):
    html = client.get("/expenses/5/edit").get_data(as_text=True)
    assert 'value="120.00"' in html
    assert 'value="135.50"' in html
    assert 'value="50.00"' in html
    assert '<option value="therapy" selected>' in html


def test_edit_saves(client, data_dir):
    form = {**VALID, "category": "therapy", "provider": "Harborview Physical Therapy (fictional)",
            "description": "Physical therapy session", "estimated": "120", "actual": "135.50", "paid": "135.50"}
    response = post(client, form, url="/expenses/5/edit")
    assert response.status_code == 302
    updated = expense(data_dir, 5)
    assert updated["paid_cents"] == 13550
    assert expenses.status(updated) == "paid"
    assert "updated_at" in updated


def test_invalid_edit_writes_nothing(client, data_dir):
    before = stored(data_dir)
    assert post(client, {**VALID, "actual": "10", "paid": "20"}, url="/expenses/5/edit").status_code == 400
    assert stored(data_dir) == before


def test_mark_paid_and_unpaid(client, data_dir):
    assert post(client, {"action": "paid"}, url="/expenses/3/payment").status_code == 302
    assert expense(data_dir, 3)["paid_cents"] == 9800
    assert post(client, {"action": "unpaid"}, url="/expenses/3/payment").status_code == 302
    assert expense(data_dir, 3)["paid_cents"] == 0


def test_cannot_mark_paid_before_billed(client, data_dir):
    before = expense(data_dir, 6)
    assert post(client, {"action": "paid"}, url="/expenses/6/payment").status_code == 400
    assert expense(data_dir, 6) == before


def test_unknown_payment_action_is_rejected(client):
    assert post(client, {"action": "refund"}, url="/expenses/3/payment").status_code == 400


def test_delete_confirms_then_deletes(client, data_dir):
    assert "Delete this expense?" in client.get("/expenses/3/delete").get_data(as_text=True)
    assert len(stored(data_dir)) == 7
    assert post(client, {}, url="/expenses/3/delete").status_code == 302
    assert [x["id"] for x in stored(data_dir)] == [1, 2, 4, 5, 6, 7]


@pytest.mark.parametrize("method, path", [
    ("get", "/expenses/999/edit"), ("get", "/expenses/999/delete"),
    ("post", "/expenses/999/edit"), ("post", "/expenses/999/delete"), ("post", "/expenses/999/payment"),
])
def test_unknown_expense_is_404(client, method, path):
    if method == "get":
        assert client.get(path).status_code == 404
    else:
        assert post(client, {**VALID, "action": "paid"}, url=path).status_code == 404


@pytest.mark.parametrize("path", ["/expenses/", "/expenses/3/payment", "/expenses/3/delete", "/expenses/3/edit"])
def test_writes_without_csrf_are_rejected(client, data_dir, path):
    before = stored(data_dir)
    assert post(client, {**VALID, "action": "paid"}, url=path, token=None).status_code == 400
    assert stored(data_dir) == before


def test_user_text_is_escaped(client):
    post(client, {**VALID, "description": "<img src=x onerror=alert(1)>"})
    html = client.get("/expenses/").get_data(as_text=True)
    assert "<img src=x" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


# Persistence
def test_expense_persists_after_restart(client, data_dir):
    post(client, {**VALID, "description": "Survives restart"})
    restarted = create_app({"TESTING": True, "SECRET_KEY": "test-secret", "DATA_DIR": str(data_dir)})
    assert "Survives restart" in restarted.test_client().get("/expenses/").get_data(as_text=True)


def test_20_concurrent_expense_adds_all_persist(app, data_dir):
    jobs = [
        lambda c, t, i=i: c.post("/expenses/", data={**VALID, "description": f"Concurrent {i}", "csrf_token": t})
        for i in range(20)
    ]
    assert run_concurrently(app, jobs) == [302] * 20
    saved = stored(data_dir)
    assert len(saved) == 7 + 20
    assert len({x["id"] for x in saved}) == 27


# Linking with appointments (E5)
def test_link_to_appointment_stores_id_and_label(client, data_dir):
    post(client, {**VALID, "appointment_id": "3"})
    new = stored(data_dir)[-1]
    assert new["appointment_id"] == 3
    assert new["appointment_label"] == "Fasting blood work · Nov 4, 2026"


def test_add_link_from_appointment_prefills_form(client):
    html = client.get("/expenses/?appointment_id=2").get_data(as_text=True)
    assert '<option value="2" selected>' in html
    assert 'value="2026-11-04"' in html
    assert 'value="Dr. Rowan Teague (fictional)"' in html


def test_appointment_page_lists_linked_expenses(client):
    html = client.get("/appointments/2").get_data(as_text=True)
    panel = html.split('id="expenses-heading"')[1].split("</section>")[0]
    assert "Knee MRI" in panel
    assert "$450.00 estimated" in panel
    assert "Not billed yet" in panel


def test_deleting_appointment_keeps_its_expenses(client, data_dir):
    confirm = client.get("/appointments/2/delete").get_data(as_text=True)
    assert "1 linked expense stays in Expenses" in confirm

    from tests.test_appointments import post as appt_post
    assert appt_post(client, {}, url="/appointments/2/delete").status_code == 302
    assert 2 not in [a["id"] for a in stored(data_dir, "appointments")]

    kept = expense(data_dir, 7)
    assert kept["appointment_id"] is None
    assert kept["appointment_label"] == "Knee MRI · Nov 4, 2026"
    assert kept["estimated_cents"] == 45000 and kept["paid_cents"] == 10000
    html = client.get("/expenses/").get_data(as_text=True)
    assert "Linked appointment was deleted (Knee MRI · Nov 4, 2026)" in html


def test_dangling_appointment_id_is_tolerated(client, data_dir):
    # A crash between the two writes could leave this; pages must not break.
    records = stored(data_dir)
    records[0]["appointment_id"] = 999
    (data_dir / "expenses.json").write_text(json.dumps(records), encoding="utf-8")
    html = client.get("/expenses/").get_data(as_text=True)
    assert "Linked appointment was deleted (Flu shot · Sep 12, 2026)" in html
    assert client.get("/expenses/1/edit").status_code == 200


def test_editing_unlinked_expense_keeps_deleted_label(client, data_dir):
    from tests.test_appointments import post as appt_post
    appt_post(client, {}, url="/appointments/2/delete")
    form = {**VALID, "category": "imaging", "provider": "Lakeside Imaging Center (fictional)",
            "description": "Knee MRI", "estimated": "450", "paid": "100"}
    post(client, form, url="/expenses/7/edit")
    assert expense(data_dir, 7)["appointment_label"] == "Knee MRI · Nov 4, 2026"


def test_unlinking_on_purpose_clears_label(client, data_dir):
    form = {**VALID, "category": "imaging", "provider": "Lakeside Imaging Center (fictional)",
            "description": "Knee MRI", "estimated": "450", "paid": "100", "appointment_id": ""}
    post(client, form, url="/expenses/7/edit")
    edited = expense(data_dir, 7)
    assert edited["appointment_id"] is None
    assert edited["appointment_label"] is None


def test_expenses_page_works_with_no_appointments_file(client, data_dir):
    (data_dir / "appointments.json").unlink()
    assert client.get("/expenses/").status_code == 200
