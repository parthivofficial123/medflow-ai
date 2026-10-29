import html as html_lib
import io
import json
import re

import pytest
from flask import request

from medflow import bill_ai, bills, expenses
from tests.conftest import get_csrf_token

PDF = b"%PDF-1.4\n% fictional test bill\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16

GOOD_ANSWER = {
    "provider": "Lakeside Imaging (fictional)",
    "bill_date": "2026-10-10",
    "total": "$1,265.00",
    "items": [
        {"description": "MRI knee without contrast", "service_date": "2026-10-02",
         "amount": "$1,200.00", "explanation": "A scan of the knee using magnets."},
        {"description": "Radiologist reading", "service_date": "2026-10-02",
         "amount": "65.00", "explanation": "A doctor reviews the images."},
    ],
}


def item(**changes):
    return {"description": "Office visit", "service_date": "2026-10-02", "amount": "100.00",
            "explanation": "A visit with a clinician.", **changes}


@pytest.fixture
def fake_ai(monkeypatch):
    """Replace the one provider call. Tests never touch the network or need a key."""
    calls = []

    def set_answer(answer):
        def call_model(file_bytes, media_type):
            calls.append((file_bytes, media_type))
            if isinstance(answer, Exception):
                raise answer
            return answer if isinstance(answer, str) else json.dumps(answer)
        monkeypatch.setattr(bill_ai, "call_model", call_model)
        return calls

    return set_answer


def upload(client, content=PDF, filename="bill.pdf", token="fetch"):
    form = {}
    if token == "fetch":
        form["csrf_token"] = get_csrf_token(client, "/bills/")
    if content is not None:
        form["bill"] = (io.BytesIO(content), filename)
    return client.post("/bills/", data=form, content_type="multipart/form-data")


def files_in(data_dir):
    return sorted(p.name for p in data_dir.iterdir())


# Upload page
def test_upload_page_has_labelled_file_input_and_fictional_warning(client):
    html = client.get("/bills/").get_data(as_text=True)
    assert 'enctype="multipart/form-data"' in html
    assert '<label class="field__label" for="f-bill">' in html
    assert 'type="file"' in html and 'name="bill"' in html
    assert "fictional bills only" in html


def test_nav_links_to_bills(client):
    html = client.get("/expenses/").get_data(as_text=True)
    assert 'href="/bills/"' in html


def test_upload_requires_csrf(client, fake_ai):
    calls = fake_ai(GOOD_ANSWER)
    assert upload(client, token=None).status_code == 400
    assert calls == []


# File checks (B3)
def test_missing_file_is_rejected(client, fake_ai):
    calls = fake_ai(GOOD_ANSWER)
    response = upload(client, content=None)
    assert response.status_code == 400
    assert "Choose a bill to upload" in response.get_data(as_text=True)
    assert calls == []


@pytest.mark.parametrize("content, filename", [
    (b"just some text", "bill.txt"),
    (b"just some text", "bill.pdf"),   # right name, wrong contents
    (PDF, "bill.docx"),                # right contents, wrong name
    (PNG, "bill.pdf"),                 # contents and name disagree
    (b"", "bill.pdf"),
])
def test_wrong_file_type_is_rejected(client, fake_ai, content, filename):
    calls = fake_ai(GOOD_ANSWER)
    response = upload(client, content=content, filename=filename)
    assert response.status_code == 400
    assert "PDF, PNG or JPEG" in response.get_data(as_text=True)
    assert calls == []


@pytest.mark.parametrize("content, filename, media_type", [
    (PDF, "bill.pdf", "application/pdf"),
    (PNG, "Bill.PNG", "image/png"),
    (JPEG, "bill.jpg", "image/jpeg"),
    (JPEG, "bill.jpeg", "image/jpeg"),
])
def test_accepted_files_reach_the_ai_unchanged(client, fake_ai, content, filename, media_type):
    calls = fake_ai(GOOD_ANSWER)
    assert upload(client, content=content, filename=filename).status_code == 200
    assert calls == [(content, media_type)]


def test_file_over_5_mb_is_rejected_before_the_ai(client, fake_ai):
    calls = fake_ai(GOOD_ANSWER)
    response = upload(client, content=PDF + b"0" * (4 * 1024 * 1024))
    assert response.status_code == 413
    assert "larger than 4 MB" in response.get_data(as_text=True)
    assert calls == []


def test_large_uploads_stay_in_memory(app):
    # Werkzeug would normally spill this (over 500 KB) to a temporary file on disk.
    body = PDF + b"0" * (1024 * 1024)
    with app.test_request_context("/bills/", method="POST", content_type="multipart/form-data",
                                  data={"bill": (io.BytesIO(body), "bill.pdf")}):
        assert isinstance(request.files["bill"].stream, io.BytesIO)


# AI failures (B3)
def test_not_configured_by_default(client, data_dir):
    # The real call_model: no provider is wired in yet.
    before = files_in(data_dir)
    response = upload(client)
    assert response.status_code == 503
    assert "AI analysis isn't configured" in html_lib.unescape(response.get_data(as_text=True))
    assert files_in(data_dir) == before


@pytest.mark.parametrize("answer, status, message", [
    (bill_ai.AIError("The AI service didn't respond in time. Try again.", status=504), 504, "didn't respond in time"),
    ("this is not json", 502, "couldn't read the AI's answer"),
    ('{"items": ', 502, "couldn't read the AI's answer"),
    ([], 502, "not in the expected format"),
    ({"items": "none"}, 502, "not in the expected format"),
    ({"items": [item(amount=12)]}, 502, "not in the expected format"),
    ({"items": [{"description": "x"}]}, 502, "not in the expected format"),
    ({"items": [item()], "total": 5}, 502, "not in the expected format"),
    ({"items": []}, 422, "No charges were found"),
])
def test_ai_failures_show_a_clear_message(live_app, fake_ai, data_dir, answer, status, message):
    fake_ai(answer)
    client = live_app.test_client()
    before = (data_dir / "expenses.json").read_text(encoding="utf-8")
    response = upload(client)
    html = html_lib.unescape(response.get_data(as_text=True))
    assert response.status_code == status
    assert message in html
    assert "Traceback" not in html
    assert (data_dir / "expenses.json").read_text(encoding="utf-8") == before


# Checking the AI's answer (B2): Python decides every amount, date and total.
def test_check_answer_parses_amounts_and_dates():
    bill = bills.check_answer(GOOD_ANSWER)
    assert [i["amount_cents"] for i in bill["items"]] == [120000, 6500]
    assert [i["service_date"] for i in bill["items"]] == ["2026-10-02", "2026-10-02"]
    assert all(not i["problems"] for i in bill["items"])
    assert bill["items_total_cents"] == 126500
    assert bill["total_cents"] == 126500
    assert bill["total_matches"] is True


@pytest.mark.parametrize("amount", ["$1,2.3", "N/A", "", "12.345", "1e3"])
def test_unreadable_amount_is_flagged_not_guessed(amount):
    bill = bills.check_answer({"items": [item(amount=amount)]})
    flagged = bill["items"][0]
    assert flagged["amount_cents"] is None
    assert flagged["amount_raw"] == amount
    assert "Couldn't read this amount" in flagged["problems"][0]
    assert bill["items_total_cents"] is None


@pytest.mark.parametrize("amount", ["-$50.00", "($50.00)", "$ -5"])
def test_negative_amount_is_flagged(amount):
    flagged = bills.check_answer({"items": [item(amount=amount)]})["items"][0]
    assert flagged["amount_cents"] is None
    assert "negative" in flagged["problems"][0]


@pytest.mark.parametrize("service_date", ["10/02/2026", "", "2026-13-01", "unknown"])
def test_unreadable_date_is_flagged(service_date):
    flagged = bills.check_answer({"items": [item(service_date=service_date)]})["items"][0]
    assert flagged["service_date"] is None
    assert any("Couldn't read the date" in p for p in flagged["problems"])


def test_total_mismatch_is_reported():
    bill = bills.check_answer({"items": [item(amount="100"), item(amount="50")], "total": "$200.00"})
    assert bill["items_total_cents"] == 15000
    assert bill["total_cents"] == 20000
    assert bill["total_matches"] is False


def test_no_total_on_bill():
    bill = bills.check_answer({"items": [item()]})
    assert bill["total_cents"] is None
    assert bill["total_matches"] is None


def test_null_optional_fields_mean_not_shown():
    bill = bills.check_answer({"provider": None, "bill_date": None, "total": None, "items": [item()]})
    assert (bill["provider"], bill["bill_date"], bill["total_cents"]) == ("", None, None)


def test_unreadable_total_is_flagged_on_review_page(client, fake_ai):
    fake_ai({"items": [item(amount="100")], "total": "USD 100"})
    html = html_lib.unescape(upload(client).get_data(as_text=True))
    assert "Couldn't read the bill's total (USD 100)" in html
    assert "No total was found" not in html


def test_any_unreadable_amount_means_no_items_total():
    bill = bills.check_answer({"items": [item(amount="100"), item(amount="N/A")], "total": "100"})
    assert bill["items_total_cents"] is None
    assert bill["total_matches"] is None


def test_long_text_is_trimmed():
    bill = bills.check_answer({"items": [item(description="x" * 500, explanation="y" * 5000)]})
    assert len(bill["items"][0]["description"]) == 200
    assert len(bill["items"][0]["explanation"]) == 1000


def test_too_many_items_is_rejected():
    with pytest.raises(bill_ai.AIError, match="not in the expected format"):
        bills.check_answer({"items": [item()] * (bills.MAX_ITEMS + 1)})


# Review page (B1, B4)
def test_review_page_shows_items_explanations_and_ai_label(client, fake_ai):
    fake_ai(GOOD_ANSWER)
    html = upload(client).get_data(as_text=True)
    assert "Lakeside Imaging (fictional)" in html
    assert "MRI knee without contrast" in html
    assert "A scan of the knee using magnets." in html
    assert 'value="1200.00"' in html and 'value="65.00"' in html
    assert "On the bill: $1,200.00" in html
    assert "AI-generated explanation" in html
    assert "not medical or financial advice" in html
    assert "add up to the bill's total of $1,265.00" in html
    assert "Nothing has been saved" in html


def test_review_page_flags_problems(client, fake_ai):
    fake_ai({"items": [item(amount="N/A", service_date="soon")], "total": "$10.00"})
    html = upload(client).get_data(as_text=True)
    assert "Couldn&#39;t read this amount" in html
    assert "Couldn&#39;t read the date" in html
    assert "N/A" in html
    assert "1 item needs" in html


def test_review_page_reports_total_mismatch(client, fake_ai):
    fake_ai({"items": [item(amount="100")], "total": "$150.00"})
    html = upload(client).get_data(as_text=True)
    assert "don't add up to the bill's total" in html
    assert "$100.00" in html and "$150.00" in html


def test_ai_text_is_escaped(client, fake_ai):
    fake_ai({"provider": "<b>Clinic</b>",
             "items": [item(description="<script>alert(1)</script>", explanation="<img src=x onerror=alert(1)>")]})
    html = upload(client).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html and "&lt;b&gt;Clinic" in html


def test_upload_saves_nothing_and_writes_no_files(client, fake_ai, data_dir):
    fake_ai(GOOD_ANSWER)
    before = {name: (data_dir / name).read_text(encoding="utf-8") for name in files_in(data_dir)}
    assert upload(client).status_code == 200
    after = {name: (data_dir / name).read_text(encoding="utf-8") for name in files_in(data_dir)}
    assert after == before


def test_review_page_is_a_form_with_every_row_editable(client, fake_ai):
    fake_ai(GOOD_ANSWER)
    html = upload(client).get_data(as_text=True)
    assert 'action="/bills/save"' in html
    assert 'name="csrf_token"' in html
    assert 'name="row_count" value="2"' in html
    for i in (0, 1):
        for field in ("description", "date", "amount", "category"):
            assert f'<label class="field__label" for="f-{field}-{i}">' in html
        assert f'id="f-include-{i}"' in html
    assert 'name="provider"' in html and 'value="Lakeside Imaging (fictional)"' in html
    assert 'value="2026-10-02"' in html


def test_readable_rows_start_included_and_flagged_rows_start_excluded(client, fake_ai):
    fake_ai({"items": [item(), item(amount="N/A")]})
    html = upload(client).get_data(as_text=True)
    assert re.search(r'id="f-include-0"[^>]*checked', html)
    assert not re.search(r'id="f-include-1"[^>]*checked', html)


# Saving approved rows (B4, B5)
def save_form(**changes):
    form = {
        "review_id": "review-test-1",
        "row_count": "2",
        "provider": "Lakeside Imaging (fictional)",
        "bill_total": "$1,265.00", "bill_date": "2026-10-10",
        "include-0": "yes", "description-0": "MRI knee without contrast", "date-0": "2026-10-02",
        "amount-0": "1200.00", "category-0": "imaging", "explanation-0": "A scan.", "on_bill-0": "$1,200.00",
        "include-1": "yes", "description-1": "Radiologist reading", "date-1": "2026-10-02",
        "amount-1": "65.00", "category-1": "imaging", "explanation-1": "A review.", "on_bill-1": "65.00",
    }
    form.update(changes)
    return {k: v for k, v in form.items() if v is not None}


def save(client, form, token="fetch"):
    data = dict(form)
    if token == "fetch":
        data["csrf_token"] = get_csrf_token(client, "/bills/")
    return client.post("/bills/save", data=data)


def stored_expenses(data_dir):
    return json.loads((data_dir / "expenses.json").read_text(encoding="utf-8"))


def test_approved_rows_are_saved_as_billed_expenses(client, fake_ai, data_dir):
    calls = fake_ai(GOOD_ANSWER)
    before = stored_expenses(data_dir)
    response = save(client, save_form())
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/expenses/")
    new = stored_expenses(data_dir)[len(before):]
    assert [(e["description"], e["actual_cents"]) for e in new] == [
        ("MRI knee without contrast", 120000), ("Radiologist reading", 6500)]
    for e in new:
        assert e["source"] == "bill"
        assert e["provider"] == "Lakeside Imaging (fictional)"
        assert e["date"] == "2026-10-02"
        assert e["category"] == "imaging"
        assert e["estimated_cents"] is None
        assert e["paid_cents"] == 0
        assert e["appointment_id"] is None
        assert "explanation" not in e
    top = max(e["id"] for e in before)
    assert [e["id"] for e in new] == [top + 1, top + 2]
    assert calls == []  # saving never calls the AI again
    html = client.get("/expenses/").get_data(as_text=True)
    assert "Saved 2 expenses from the bill" in html
    assert "From a bill" in html


def test_unchecked_rows_are_not_saved(client, data_dir):
    before = len(stored_expenses(data_dir))
    assert save(client, save_form(**{"include-1": None})).status_code == 302
    new = stored_expenses(data_dir)[before:]
    assert [e["description"] for e in new] == ["MRI knee without contrast"]


def test_edited_values_are_what_gets_saved(client, data_dir):
    before = len(stored_expenses(data_dir))
    form = save_form(**{"amount-0": "$1,150.50", "description-0": "Knee MRI", "date-0": "2026-10-03",
                        "category-0": "other", "provider": "Edited Clinic (fictional)", "include-1": None})
    assert save(client, form).status_code == 302
    (e,) = stored_expenses(data_dir)[before:]
    assert (e["actual_cents"], e["description"], e["date"], e["category"], e["provider"]) == (
        115050, "Knee MRI", "2026-10-03", "other", "Edited Clinic (fictional)")


def test_zero_dollar_charge_is_kept_as_zero_not_unknown(client, data_dir):
    before = len(stored_expenses(data_dir))
    assert save(client, save_form(**{"amount-0": "0", "include-1": None})).status_code == 302
    (e,) = stored_expenses(data_dir)[before:]
    assert e["actual_cents"] == 0


@pytest.mark.parametrize("changes, field, message", [
    ({"amount-0": "N/A"}, "amount-0", "Enter an amount like"),
    ({"amount-0": ""}, "amount-0", "Enter the amount from the bill"),
    ({"amount-0": "-5"}, "amount-0", "can't be negative"),
    ({"date-0": ""}, "date-0", "Date of service is required"),
    ({"date-0": "10/02/2026"}, "date-0", "Enter a valid date"),
    ({"category-0": "spa"}, "category-0", "Choose a category"),
    ({"category-1": ""}, "category-1", "Choose a category"),
    ({"description-1": "x" * 201}, "description-1", "200 characters"),
    ({"provider": ""}, "provider", "Provider is required"),
    ({"provider": "p" * 101}, "provider", "100 characters"),
    ({"include-0": None, "include-1": None}, "rows", "Select at least one charge"),
])
def test_invalid_rows_save_nothing_and_keep_input(client, data_dir, changes, field, message):
    before = (data_dir / "expenses.json").read_text(encoding="utf-8")
    response = save(client, save_form(**changes))
    html = html_lib.unescape(response.get_data(as_text=True))
    assert response.status_code == 400
    assert message in html
    assert f'href="#f-{field}"' in html
    assert (data_dir / "expenses.json").read_text(encoding="utf-8") == before
    assert 'value="Radiologist reading"' in html or field == "description-1"
    assert "A scan." in html  # the explanation is shown again


def test_errors_on_excluded_rows_are_ignored(client, data_dir):
    before = len(stored_expenses(data_dir))
    assert save(client, save_form(**{"include-1": None, "amount-1": "N/A"})).status_code == 302
    assert len(stored_expenses(data_dir)) == before + 1


@pytest.mark.parametrize("row_count", ["", "abc", "0", "-1", str(bills.MAX_ITEMS + 1)])
def test_tampered_row_count_is_rejected(client, data_dir, row_count):
    before = (data_dir / "expenses.json").read_text(encoding="utf-8")
    assert save(client, save_form(row_count=row_count)).status_code == 400
    assert (data_dir / "expenses.json").read_text(encoding="utf-8") == before


def test_save_requires_csrf(client, data_dir):
    before = (data_dir / "expenses.json").read_text(encoding="utf-8")
    assert save(client, save_form(), token=None).status_code == 400
    assert (data_dir / "expenses.json").read_text(encoding="utf-8") == before


def test_saved_bill_counts_in_the_expense_summary(client, data_dir):
    billed_before = expenses.summarize(stored_expenses(data_dir))["billed"]
    assert save(client, save_form()).status_code == 302
    assert expenses.summarize(stored_expenses(data_dir))["billed"] == billed_before + 126500


def test_explanation_is_escaped_when_redisplayed(client):
    response = save(client, save_form(**{"explanation-0": "<script>alert(1)</script>", "amount-0": "N/A"}))
    html = response.get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.parametrize("bill_date", ["not a date", "2026-13-40", "<b>x</b>"])
def test_tampered_bill_date_is_not_shown(client, bill_date):
    response = save(client, save_form(bill_date=bill_date, **{"amount-0": "N/A"}))
    assert response.status_code == 400
    assert "Bill dated" not in response.get_data(as_text=True)


def test_unreadable_date_from_the_bill_is_shown_as_a_hint(client, fake_ai):
    fake_ai({"items": [item(service_date="10/02/2026")]})
    html = upload(client).get_data(as_text=True)
    assert "On the bill: 10/02/2026" in html


def test_ai_warnings_survive_a_failed_save(client, fake_ai):
    fake_ai({"items": [item(), item(amount="N/A")]})
    html = upload(client).get_data(as_text=True)
    problems = re.search(r'name="problems-1" value="([^"]*)"', html).group(1)
    form = save_form(**{"problems-1": html_lib.unescape(problems), "include-1": None, "date-0": ""})
    html = html_lib.unescape(save(client, form).get_data(as_text=True))
    assert "Couldn't read this amount" in html
    assert "1 item needs" in html


def test_each_checkbox_label_names_its_charge(client, fake_ai):
    fake_ai(GOOD_ANSWER)
    html = upload(client).get_data(as_text=True)
    assert "Save charge 1<span class=\"visually-hidden\">: MRI knee without contrast</span>" in html


def test_review_totals_follow_the_edited_rows(client):
    html = html_lib.unescape(save(client, save_form(**{"amount-1": "N/A"})).get_data(as_text=True))
    assert "No total is shown until every amount has been read" in html
    html = html_lib.unescape(save(client, save_form(**{"category-1": ""})).get_data(as_text=True))
    assert "add up to the bill's total of $1,265.00" in html


# The provider module
def test_extract_parses_json_from_call_model(fake_ai):
    fake_ai(GOOD_ANSWER)
    assert bill_ai.extract(PDF, "application/pdf") == GOOD_ANSWER


def test_prompt_treats_bill_text_as_data():
    assert "not instructions" in bill_ai.PROMPT
    assert "exactly as printed" in bill_ai.PROMPT


# The whole path with the real Gemini client: only the network and the clock are faked.

@pytest.fixture
def gemini_replies(monkeypatch):
    """Make urlopen answer with each given reply in turn; waits take no real time."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(bill_ai, "sleep", lambda seconds: None)
    calls = []

    def set_replies(*replies):
        def urlopen(request, timeout):
            reply = replies[min(len(calls), len(replies) - 1)]
            calls.append(timeout)
            if isinstance(reply, Exception):
                raise reply
            text = reply if isinstance(reply, str) else json.dumps(reply)
            body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}
            return io.BytesIO(json.dumps(body).encode())
        monkeypatch.setattr(bill_ai.urllib.request, "urlopen", urlopen)
        return calls

    return set_replies


def busy():
    return bill_ai.urllib.error.HTTPError("https://gemini.invalid/", 503, "busy", {}, io.BytesIO(b"{}"))


def test_upload_survives_a_busy_ai_service(client, gemini_replies, data_dir):
    calls = gemini_replies(busy(), GOOD_ANSWER)
    response = upload(client)
    assert response.status_code == 200
    assert "MRI knee without contrast" in response.get_data(as_text=True)
    assert len(calls) == 2
    assert files_in(data_dir) == ["appointments.json", "expenses.json"]  # the bill was never written


def test_upload_reports_a_service_that_stays_busy(client, gemini_replies):
    calls = gemini_replies(busy())
    response = upload(client)
    assert response.status_code == 502
    assert "having problems" in response.get_data(as_text=True)
    assert len(calls) == bill_ai.MAX_ATTEMPTS


def test_upload_reports_a_timeout(client, gemini_replies):
    gemini_replies(TimeoutError("timed out"))
    response = upload(client)
    assert response.status_code == 504
    assert "didn&#39;t respond in time" in response.get_data(as_text=True)


def test_upload_reports_a_malformed_answer_without_retrying(client, gemini_replies):
    calls = gemini_replies("{not json", GOOD_ANSWER)
    response = upload(client)
    assert response.status_code == 502
    assert "couldn&#39;t read the AI&#39;s answer" in response.get_data(as_text=True)
    assert len(calls) == 1


# A second click while a bill is being read or saved is ignored (public/static/js/app.js).

def test_upload_and_save_forms_opt_in_to_the_double_submit_guard(client, fake_ai):
    upload_page = client.get("/bills/").get_data(as_text=True)
    assert 'data-busy-label="Reading your bill' in upload_page
    assert "data-busy-status" in upload_page and 'role="status"' in upload_page
    fake_ai(GOOD_ANSWER)
    review_page = upload(client).get_data(as_text=True)
    assert 'data-busy-label="Saving' in review_page


def test_pages_load_the_script_deferred(client):
    html = client.get("/bills/").get_data(as_text=True)
    assert '<script src="/static/js/app.js" defer></script>' in html
    assert client.get("/static/js/app.js").status_code == 200


def test_the_review_form_carries_a_one_time_review_id(client, fake_ai):
    fake_ai(GOOD_ANSWER)
    first = upload(client).get_data(as_text=True)
    second = upload(client).get_data(as_text=True)
    ids = [re.search(r'name="review_id" value="([^"]+)"', html).group(1) for html in (first, second)]
    assert len(ids[0]) >= 16 and ids[0] != ids[1]


def test_saving_the_same_review_twice_adds_nothing_the_second_time(client, data_dir):
    first = save(client, save_form())
    count = len(stored_expenses(data_dir))
    again = save(client, save_form())  # e.g. Back to the review page, then Save again
    assert first.status_code == again.status_code == 302
    assert len(stored_expenses(data_dir)) == count
    assert "already saved" in html_lib.unescape(client.get("/expenses/").get_data(as_text=True))


def test_a_different_review_of_the_same_bill_can_still_be_saved(client, data_dir):
    save(client, save_form())
    count = len(stored_expenses(data_dir))
    save(client, save_form(review_id="review-test-2"))
    assert len(stored_expenses(data_dir)) == count + 2


@pytest.mark.parametrize("review_id", [None, "", "x" * 65])
def test_a_save_without_a_valid_review_id_is_rejected(client, data_dir, review_id):
    before = stored_expenses(data_dir)
    assert save(client, save_form(review_id=review_id)).status_code == 400
    assert stored_expenses(data_dir) == before
