import os

from flask import Blueprint, render_template, request

from . import bill_ai, dates, expenses

bp = Blueprint("bills", __name__, url_prefix="/bills")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_ITEMS = 100
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
    return render_template("bills/review.html", bill=bill)
