import os
import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from . import bill_ai, dates, expenses, storage

bp = Blueprint("bills", __name__, url_prefix="/bills")

# Vercel rejects request bodies over 4.5 MB.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_ITEMS = 100
# Review ids of recent saves, kept in the session so Back + Save can't save a bill twice.
SAVED_REVIEWS_KEPT = 20
# The file's first bytes decide its type; the name only has to agree with them.
FILE_TYPES = {
    "application/pdf": ((b"%PDF-",), (".pdf",)),
    "image/png": ((b"\x89PNG\r\n\x1a\n",), (".png",)),
    "image/jpeg": ((b"\xff\xd8\xff",), (".jpg", ".jpeg")),
}
TEXT_LIMITS = {"description": 200, "explanation": 1000, "provider": 100}
ITEM_FIELDS = ("description", "service_date", "amount", "explanation")


def media_type_of(content, filename):
    """The bill's media type, or None if it isn't a PDF, PNG or JPEG."""
    extension = os.path.splitext(filename or "")[1].lower()
    for media_type, (signatures, extensions) in FILE_TYPES.items():
        if content.startswith(signatures) and extension in extensions:
            return media_type
    return None


def bad_format():
    return bill_ai.AIError("The AI's answer was not in the expected format, so MedFlow "
                           "didn't use it. Try again.")


def text(value, field):
    # Models sometimes send null for "not shown"; that means the same as "".
    if value is None:
        return ""
    if not isinstance(value, str):
        raise bad_format()
    value = value.strip()
    return value[:TEXT_LIMITS[field]] if field in TEXT_LIMITS else value


def check_item(raw):
    if not isinstance(raw, dict) or any(f not in raw for f in ITEM_FIELDS):
        raise bad_format()
    item = {f: text(raw[f], f) for f in ITEM_FIELDS}
    problems = []

    cents, error = expenses.parse_money(item["amount"])
    # Bills print credits as "-$50.00" or "($50.00)".
    if error and item["amount"].lstrip("$ ").startswith(("-", "(")):
        problems.append("This amount is negative, likely a payment or adjustment. MedFlow only reads charges.")
    elif cents is None:
        problems.append("Couldn't read this amount. Check it on your bill.")

    service_date, error = dates.check_date(item["service_date"])
    if error:
        problems.append("Couldn't read the date of service.")
        service_date = None

    return {
        "description": item["description"],
        "explanation": item["explanation"],
        "amount_raw": item["amount"],
        "amount_cents": cents,
        "service_date": service_date,
        "service_date_raw": item["service_date"],
        "problems": problems,
    }


def check_answer(answer):
    """Turn the model's answer into a bill the review page can show, deciding every number in Python.

    Raises AIError if the answer isn't shaped like bill_ai.ANSWER_SCHEMA. Amounts and dates
    that don't parse are kept and flagged, never guessed. The items total is only given
    when every amount was readable.
    """
    if not isinstance(answer, dict) or not isinstance(answer.get("items"), list):
        raise bad_format()
    if len(answer["items"]) > MAX_ITEMS:
        raise bad_format()
    items = [check_item(raw) for raw in answer["items"]]

    total_raw = text(answer.get("total"), "total")
    total_cents, _ = expenses.parse_money(total_raw)
    items_total = None
    if items and all(i["amount_cents"] is not None for i in items):
        items_total = sum(i["amount_cents"] for i in items)
    bill_date, error = dates.check_date(text(answer.get("bill_date"), "bill_date"))
    return {
        "provider": text(answer.get("provider"), "provider"),
        "bill_date": None if error else bill_date,
        "items": items,
        "problem_count": sum(1 for i in items if i["problems"]),
        "items_total_cents": items_total,
        "total_raw": total_raw,
        "total_cents": total_cents,
        "total_matches": None if items_total is None or total_cents is None else items_total == total_cents,
    }


def render_upload(error, status_code):
    return render_template("bills/upload.html", error=error), status_code


@bp.get("/")
def upload_form():
    return render_template("bills/upload.html", error=None)


@bp.post("/")
def analyze():
    file = request.files.get("bill")
    if file is None or not file.filename:
        return render_upload("Choose a bill to upload.", 400)
    content = file.read()
    media_type = media_type_of(content, file.filename)
    if media_type is None:
        return render_upload("That file isn't a PDF, PNG or JPEG. Upload a bill in one of those formats.", 400)

    try:
        bill = check_answer(bill_ai.extract(content, media_type))
    except bill_ai.AIError as e:
        return render_upload(e.message, e.status)
    if not bill["items"]:
        return render_upload("No charges were found on this bill. Check that it's a medical bill "
                             "and that the file is readable, then try again.", 422)
    return render_review(review_form(bill))


def review_form(bill):
    """The review form's starting values. Rows the AI read cleanly start included; flagged rows don't."""
    form = {
        "review_id": secrets.token_urlsafe(16),
        "row_count": str(len(bill["items"])),
        "provider": bill["provider"],
        "bill_date": bill["bill_date"] or "",
        "bill_total": bill["total_raw"],
    }
    for i, item in enumerate(bill["items"]):
        cents = item["amount_cents"]
        form.update({
            f"include-{i}": "" if item["problems"] else "yes",
            f"description-{i}": item["description"],
            # A date input can't show "10/02/2026", so an unreadable date starts blank with a hint.
            f"date-{i}": item["service_date"] or "",
            f"date_raw-{i}": item["service_date_raw"],
            # Kept in the form so the warnings survive a re-render after a failed save.
            f"problems-{i}": "\n".join(item["problems"]),
            f"amount-{i}": item["amount_raw"] if cents is None else expenses.cents_to_input(cents),
            f"category-{i}": "other",
            f"explanation-{i}": item["explanation"],
            f"on_bill-{i}": item["amount_raw"],
        })
    return form


def row_count(form):
    """How many rows the review form has. It comes back from the browser, so it's checked."""
    try:
        count = int(form.get("row_count", ""))
    except ValueError:
        count = 0
    if not 1 <= count <= MAX_ITEMS:
        abort(400, description="This review form is incomplete. Upload the bill again.")
    return count


def review_totals(form, count):
    """Totals of the included rows as they now stand, decided in Python, never by the AI."""
    included = [i for i in range(count) if form.get(f"include-{i}") == "yes"]
    amounts = [expenses.parse_money(form.get(f"amount-{i}", ""))[0] for i in included]
    items_total = sum(amounts) if included and None not in amounts else None
    bill_total = form.get("bill_total", "")
    total_cents = expenses.parse_money(bill_total)[0]
    return {
        "selected": len(included),
        "items_total_cents": items_total,
        "total_raw": bill_total,
        "total_cents": total_cents,
        "total_matches": None if items_total is None or total_cents is None else items_total == total_cents,
    }


def render_review(form, errors=None, status_code=200):
    count = row_count(form)
    problems = [form.get(f"problems-{i}", "").splitlines() for i in range(count)]
    # bill_date comes back from the browser on a re-render, so only a valid date is shown.
    bill_date, error = dates.check_date(form.get("bill_date", ""))
    return render_template(
        "bills/review.html",
        form=form,
        bill_date=None if error else bill_date,
        rows=[{"index": i, "problems": problems[i]} for i in range(count)],
        problem_count=sum(1 for p in problems if p),
        totals=review_totals(form, count),
        errors=errors or {},
    ), status_code


# Row fields map onto the expense form so bills reuse the exact expense validation.
EXPENSE_FIELDS = {"date": "date", "description": "description", "category": "category", "actual": "amount"}


def validate_rows(form, count):
    """Return (expense records for the included rows, errors keyed by form field name)."""
    errors = {}
    provider = form.get("provider", "")
    records = []
    for i in range(count):
        if form.get(f"include-{i}") != "yes":
            continue
        amount = form.get(f"amount-{i}", "")
        data, row_errors = expenses.validate({
            "date": form.get(f"date-{i}", ""),
            "provider": provider,
            "description": form.get(f"description-{i}", ""),
            "category": form.get(f"category-{i}", ""),
            "actual": amount,
        }, appointments=[])
        if not amount.strip():
            row_errors["actual"] = "Enter the amount from the bill, or untick this charge."
        if "provider" in row_errors:
            errors.setdefault("provider", row_errors.pop("provider"))
        row_errors.pop("estimated", None)  # only says "enter an amount", covered above
        for name, message in row_errors.items():
            errors[f"{EXPENSE_FIELDS[name]}-{i}"] = message
        records.append(data)
    if not records and not errors:
        errors["rows"] = "Select at least one charge to save."
    return records, errors


@bp.post("/save")
def save():
    review_id = request.form.get("review_id", "")
    if not 1 <= len(review_id) <= 64:
        abort(400, description="This review form is incomplete. Upload the bill again.")
    saved_reviews = session.get("saved_reviews", [])
    if review_id in saved_reviews:
        flash("These charges were already saved, so nothing was added again.", "success")
        return redirect(url_for("expenses.index"))
    count = row_count(request.form)
    records, errors = validate_rows(request.form, count)
    if errors:
        return render_review(request.form, errors, 400)

    with storage.modify("expenses") as stored:
        for data in records:
            stored.append({"id": storage.next_id(stored), **data, "source": "bill",
                           "created_at": expenses.now_iso()})
    session["saved_reviews"] = (saved_reviews + [review_id])[-SAVED_REVIEWS_KEPT:]
    n = len(records)
    flash(f"Saved {n} {'expense' if n == 1 else 'expenses'} from the bill. "
          "Record payments here as you make them.", "success")
    return redirect(url_for("expenses.index"))
