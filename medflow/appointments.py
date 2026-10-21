from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from . import storage

bp = Blueprint("appointments", __name__, url_prefix="/appointments")

# field: (label, required, max length)
FIELDS = {
    "date": ("Date", True, 10),
    "time": ("Time", True, 5),
    "provider": ("Provider", True, 100),
    "location": ("Location", False, 120),
    "reason": ("Reason for visit", True, 120),
    "notes": ("Notes", False, 1000),
}


def validate(form):
    """Return (clean data, errors). Values are kept even when invalid so the form can redisplay them."""
    data = {name: form.get(name, "").strip() for name in FIELDS}
    errors = {}
    for name, (label, required, max_len) in FIELDS.items():
        if required and not data[name]:
            errors[name] = f"{label} is required."
        elif len(data[name]) > max_len:
            errors[name] = f"{label} must be {max_len} characters or fewer."

    if "date" not in errors:
        try:
            year = datetime.strptime(data["date"], "%Y-%m-%d").year
            if not 2000 <= year <= 2100:
                errors["date"] = "Enter a date between 2000 and 2100."
        except ValueError:
            errors["date"] = "Enter a valid date (YYYY-MM-DD)."
    if "time" not in errors:
        try:
            datetime.strptime(data["time"], "%H:%M")
        except ValueError:
            errors["time"] = "Enter a valid time (HH:MM)."
    return data, errors


def render_page(form=None, errors=None, status=200):
    records = sorted(storage.load("appointments"), key=lambda a: (a["date"], a["time"]))
    return render_template(
        "appointments/list.html", appointments=records, form=form or {}, errors=errors or {}
    ), status


@bp.get("/")
def index():
    return render_page()


@bp.post("/")
def create():
    data, errors = validate(request.form)
    if errors:
        return render_page(form=data, errors=errors, status=400)

    records = storage.load("appointments")
    records.append({
        "id": storage.next_id(records),
        **data,
        "status": "scheduled",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    storage.save("appointments", records)
    flash(f"Added: {data['reason']} with {data['provider']}.", "success")
    return redirect(url_for(".index"))
