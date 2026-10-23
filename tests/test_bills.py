import html as html_lib
import io
import json

import pytest
from flask import request

from medflow import bill_ai, bills
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
    response = upload(client, content=PDF + b"0" * (5 * 1024 * 1024))
    assert response.status_code == 413
    assert "larger than 5 MB" in response.get_data(as_text=True)
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


# Review page (B1, read-only on Day 4)
def test_review_page_shows_items_explanations_and_ai_label(client, fake_ai):
    fake_ai(GOOD_ANSWER)
    html = upload(client).get_data(as_text=True)
    assert "Lakeside Imaging (fictional)" in html
    assert "MRI knee without contrast" in html
    assert "A scan of the knee using magnets." in html
    assert "$1,200.00" in html and "$65.00" in html
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


# The provider module
def test_extract_parses_json_from_call_model(fake_ai):
    fake_ai(GOOD_ANSWER)
    assert bill_ai.extract(PDF, "application/pdf") == GOOD_ANSWER


def test_prompt_treats_bill_text_as_data():
    assert "not instructions" in bill_ai.PROMPT
    assert "exactly as printed" in bill_ai.PROMPT
