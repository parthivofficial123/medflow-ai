import re
from datetime import datetime
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from . import dates, storage

bp = Blueprint("expenses", __name__, url_prefix="/expenses")

CATEGORIES = {
    "visit": "Doctor visit",
    "imaging": "Imaging",
    "lab": "Lab tests",
    "pharmacy": "Pharmacy",
    "dental": "Dental",
    "vision": "Vision",
    "therapy": "Therapy",
    "other": "Other",
}
STATUS_LABELS = {
    "not_billed": "Not billed yet",
    "unpaid": "Unpaid",
    "partly_paid": "Partly paid",
    "paid": "Paid",
}
MAX_CENTS = 100_000_000  # $1,000,000
# ASCII digits with optional correctly placed thousands commas, then optional decimals.
# Anything else (negatives, NaN, 1e5, "1,23", non-ASCII digits like "٣") never reaches Decimal.
_MONEY = re.compile(r"(\d{1,3}(,\d{3})+|\d+)(\.\d+)?", re.ASCII)


def parse_money(raw):
    """Return (cents or None, error). Blank means "no amount" (None), never 0."""
    text = raw.strip().removeprefix("$").strip()
    if not text:
        return None, None
    if text.startswith("-"):
        return None, "Amounts can't be negative."
    if not _MONEY.fullmatch(text):
        return None, "Enter an amount like 120, 120.50 or 1,234.56."
    cents = Decimal(text.replace(",", "")) * 100
    if cents != cents.to_integral_value():
        return None, "Use at most 2 decimal places (cents)."
    if cents > MAX_CENTS:
        return None, "Amounts must be $1,000,000 or less."
    return int(cents), None


def cents_to_input(cents):
    """Cents -> the text a user would type, for prefilling forms."""
    if cents is None:
        return ""
    dollars, rest = divmod(cents, 100)
    return f"{dollars}.{rest:02d}"


def status(expense):
    actual, paid = expense.get("actual_cents"), expense.get("paid_cents", 0)
    if actual is None:
        return "not_billed"
    if paid >= actual:
        return "paid"
    return "unpaid" if paid == 0 else "partly_paid"


def summarize(expenses):
    """Totals per docs/PLAN.md "Expense specification". Each is separate; none is a sum of others.

    estimated          all estimates that were entered
    billed             known actual amounts (null = unknown, skipped; 0 counts as $0)
    billed_count       how many have a known actual, so "no bills yet" isn't shown as $0.00
    paid               everything recorded as paid
    unpaid_billed      what recorded bills still show as unpaid; estimates never count
    pending_estimates  estimates for expenses that have no bill yet
    compared_*         estimate vs. actual, only over expenses that have both
    """
    t = dict.fromkeys(
        ("estimated", "billed", "billed_count", "paid", "unpaid_billed", "pending_estimates",
         "compared_count", "compared_estimated", "compared_actual"), 0)
    for e in expenses:
        estimated, actual, paid = e.get("estimated_cents"), e.get("actual_cents"), e.get("paid_cents", 0)
        t["paid"] += paid
        if estimated is not None:
            t["estimated"] += estimated
        if actual is None:
            if estimated is not None:
                t["pending_estimates"] += estimated
            continue
        t["billed"] += actual
        t["billed_count"] += 1
        t["unpaid_billed"] += max(actual - paid, 0)
        if estimated is not None:
            t["compared_count"] += 1
            t["compared_estimated"] += estimated
            t["compared_actual"] += actual
    return t


def summary_view(expenses):
    month = dates.today().strftime("%Y-%m")
    by_category = {
        key: summarize([e for e in expenses if e["category"] == key])
        for key in CATEGORIES
        if any(e["category"] == key for e in expenses)
    }
    return {
        "month_label": dates.today().strftime("%B %Y"),
        "month": summarize([e for e in expenses if e["date"].startswith(month)]),
        "all": summarize(expenses),
        "by_category": by_category,
    }


def appointment_label(appt):
    d = datetime.strptime(appt["date"], "%Y-%m-%d")
    return f"{appt['reason']} · {d:%b} {d.day}, {d.year}"


def appointment_choices(appointments):
    choices = {"": "No linked appointment"}
    for a in sorted(appointments, key=lambda a: (a["date"], a["time"]), reverse=True):
        choices[str(a["id"])] = appointment_label(a)
    return choices


def validate(form, appointments):
    """Return (clean record fields, errors). The form redisplays request.form itself on errors."""
    data = {
        "provider": form.get("provider", "").strip(),
        "description": form.get("description", "").strip(),
        "category": form.get("category", "").strip(),
    }
    errors = {}

    data["date"], error = dates.check_date(form.get("date", ""), label="Date of service")
    if error:
        errors["date"] = error
    if not data["provider"]:
        errors["provider"] = "Provider is required."
    elif len(data["provider"]) > 100:
        errors["provider"] = "Provider must be 100 characters or fewer."
    if len(data["description"]) > 200:
        errors["description"] = "Description must be 200 characters or fewer."
    if data["category"] not in CATEGORIES:
        errors["category"] = "Choose a category from the list."

    for field in ("estimated", "actual", "paid"):
        data[f"{field}_cents"], error = parse_money(form.get(field, ""))
        if error:
            errors[field] = error
    if data["paid_cents"] is None:
        data["paid_cents"] = 0
    if "estimated" not in errors and "actual" not in errors \
            and data["estimated_cents"] is None and data["actual_cents"] is None:
        errors["estimated"] = "Enter an estimated amount, a billed amount, or both."
    if "paid" not in errors and data["actual_cents"] is not None and data["paid_cents"] > data["actual_cents"]:
        errors["paid"] = "Paid can't be more than the billed amount."

    raw_id = form.get("appointment_id", "").strip()
    data["appointment_id"], data["appointment_label"] = None, None
    if raw_id:
        appt = next((a for a in appointments if str(a["id"]) == raw_id), None)
        if appt is None:
            errors["appointment_id"] = "Choose an appointment from the list."
        else:
            data["appointment_id"], data["appointment_label"] = appt["id"], appointment_label(appt)
    return data, errors


def as_form(expense):
    """A stored expense -> form values for the edit page."""
    return {
        **expense,
        "estimated": cents_to_input(expense.get("estimated_cents")),
        "actual": cents_to_input(expense.get("actual_cents")),
        "paid": cents_to_input(expense.get("paid_cents") or None),
        "appointment_id": "" if expense.get("appointment_id") is None else str(expense["appointment_id"]),
    }


def find(records, expense_id):
    for e in records:
        if e["id"] == expense_id:
            return e
    abort(404)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def render_list(form=None, errors=None, status_code=200):
    expenses = sorted(storage.load("expenses"), key=lambda e: (e["date"], e["id"]), reverse=True)
    appointments = storage.load("appointments")
    return render_template(
        "expenses/list.html",
        expenses=expenses,
        summary=summary_view(expenses),
        appointment_ids={a["id"] for a in appointments},
        appointment_choices=appointment_choices(appointments),
        form=form or {},
        errors=errors or {},
    ), status_code


# App-wide: the appointment page lists linked expenses with the same labels.
@bp.app_context_processor
def inject_choices():
    return {
        "categories": CATEGORIES,
        "category_choices": {"": "Choose…", **CATEGORIES},
        "status_labels": STATUS_LABELS,
        "expense_status": status,
    }


@bp.get("/")
def index():
    # "Add expense" from an appointment page prefills the link, date and provider.
    form = {}
    appt_id = request.args.get("appointment_id", "")
    appt = next((a for a in storage.load("appointments") if str(a["id"]) == appt_id), None)
    if appt:
        form = {"appointment_id": appt_id, "date": appt["date"], "provider": appt["provider"]}
    return render_list(form=form)


@bp.post("/")
def create():
    data, errors = validate(request.form, storage.load("appointments"))
    if errors:
        return render_list(form=request.form, errors=errors, status_code=400)

    with storage.modify("expenses") as records:
        records.append({"id": storage.next_id(records), **data, "created_at": now_iso()})
    flash(f"Expense added: {data['description'] or CATEGORIES[data['category']]} ({data['provider']}).", "success")
    return redirect(url_for(".index"))


@bp.get("/<int:expense_id>/edit")
def edit(expense_id):
    expense = find(storage.load("expenses"), expense_id)
    return render_edit(expense, as_form(expense), {})


def render_edit(expense, form, errors, status_code=200):
    return render_template(
        "expenses/edit.html",
        e=expense,
        form=form,
        errors=errors,
        appointment_choices=appointment_choices(storage.load("appointments")),
    ), status_code


@bp.post("/<int:expense_id>/edit")
def update(expense_id):
    data, errors = validate(request.form, storage.load("appointments"))
    if errors:
        return render_edit(find(storage.load("expenses"), expense_id), request.form, errors, 400)

    with storage.modify("expenses") as records:
        expense = find(records, expense_id)
        # Keep the label of an appointment that was deleted unless the user links a new one.
        if data["appointment_id"] is None and expense.get("appointment_id") is None:
            data["appointment_label"] = expense.get("appointment_label")
        expense.update(data, updated_at=now_iso())
    flash("Expense updated.", "success")
    return redirect(url_for(".index") + f"#expense-{expense_id}")


@bp.post("/<int:expense_id>/payment")
def set_payment(expense_id):
    action = request.form.get("action")
    if action not in ("paid", "unpaid"):
        abort(400, description="Unknown payment action.")
    with storage.modify("expenses") as records:
        expense = find(records, expense_id)
        if action == "paid":
            if expense.get("actual_cents") is None:
                abort(400, description="Record the billed amount before marking this expense paid.")
            expense["paid_cents"] = expense["actual_cents"]
        else:
            expense["paid_cents"] = 0
        expense["updated_at"] = now_iso()
    flash(f"Marked as {action}.", "success")
    return redirect(url_for(".index") + f"#expense-{expense_id}")


@bp.get("/<int:expense_id>/delete")
def confirm_delete(expense_id):
    return render_template("expenses/confirm_delete.html", e=find(storage.load("expenses"), expense_id))


@bp.post("/<int:expense_id>/delete")
def delete(expense_id):
    with storage.modify("expenses") as records:
        expense = find(records, expense_id)
        records.remove(expense)
    flash(f"Expense deleted: {expense['description'] or CATEGORIES.get(expense['category'], 'expense')}.", "success")
    return redirect(url_for(".index"))


def linked_to(appointment_id):
    """Expenses linked to one appointment, for the appointment page."""
    return [e for e in storage.load("expenses") if e.get("appointment_id") == appointment_id]


def unlink_appointment(appointment_id):
    """Called before an appointment is deleted: keep the expenses, drop the link, keep the label."""
    with storage.modify("expenses") as records:
        for e in records:
            if e.get("appointment_id") == appointment_id:
                e["appointment_id"] = None
