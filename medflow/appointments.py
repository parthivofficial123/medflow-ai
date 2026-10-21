from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

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
STATUSES = ("scheduled", "completed", "cancelled")
# form value -> label; "" means no reminder, otherwise days before the visit
REMINDER_CHOICES = {
    "": "No reminder",
    "0": "On the day",
    "1": "1 day before",
    "2": "2 days before",
    "3": "3 days before",
    "7": "1 week before",
}
TASK_MAX = 200


def today():
    # A function rather than date.today() inline so tests can pin the date.
    return date.today()


@bp.context_processor
def inject_choices():
    return {"statuses": STATUSES, "reminder_choices": REMINDER_CHOICES, "today": today()}


def validate(form):
    """Return (clean data, errors). Values are kept even when invalid so the form can redisplay them.

    Valid dates and times are stored in canonical form (YYYY-MM-DD, HH:MM): sorting,
    the upcoming/past split and reminders all compare them as strings.
    """
    data = {name: form.get(name, "").strip() for name in FIELDS}
    errors = {}
    for name, (label, required, max_len) in FIELDS.items():
        if required and not data[name]:
            errors[name] = f"{label} is required."
        elif len(data[name]) > max_len:
            errors[name] = f"{label} must be {max_len} characters or fewer."

    if "date" not in errors:
        try:
            parsed = datetime.strptime(data["date"], "%Y-%m-%d")
            if not 2000 <= parsed.year <= 2100:
                errors["date"] = "Enter a date between 2000 and 2100."
            else:
                data["date"] = parsed.strftime("%Y-%m-%d")
        except ValueError:
            errors["date"] = "Enter a valid date (YYYY-MM-DD)."
    if "time" not in errors:
        try:
            data["time"] = datetime.strptime(data["time"], "%H:%M").strftime("%H:%M")
        except ValueError:
            errors["time"] = "Enter a valid time (HH:MM)."

    reminder = form.get("reminder_days_before", "").strip()
    if reminder in REMINDER_CHOICES:
        data["reminder_days_before"] = int(reminder) if reminder else None
    else:
        data["reminder_days_before"] = None
        errors["reminder_days_before"] = "Choose a reminder from the list."
    return data, errors


def reminder_due(appt, on):
    """Due from N days before the visit through the visit day, unless dismissed or not scheduled."""
    days = appt.get("reminder_days_before")
    if days is None or appt.get("reminder_dismissed") or appt.get("status") != "scheduled":
        return False
    visit = date.fromisoformat(appt["date"])
    return visit - timedelta(days=days) <= on <= visit


def find(records, appt_id):
    for appt in records:
        if appt["id"] == appt_id:
            return appt
    abort(404)


def find_task(appt, task_id):
    for task in appt.get("tasks", []):
        if task["id"] == task_id:
            return task
    abort(404)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def render_list(form=None, errors=None, status=200):
    records = storage.load("appointments")
    on, cutoff = today(), today().isoformat()
    by_time = lambda a: (a["date"], a["time"])
    upcoming = sorted((a for a in records if a["date"] >= cutoff), key=by_time)
    past = sorted((a for a in records if a["date"] < cutoff), key=by_time, reverse=True)
    return render_template(
        "appointments/list.html",
        upcoming=upcoming,
        past=past,
        due=[a for a in upcoming if reminder_due(a, on)],
        form=form or {},
        errors=errors or {},
    ), status


def render_detail(appt, task_text="", task_error=None, status=200):
    days = appt.get("reminder_days_before")
    remind_on = None
    if days is not None:
        remind_on = (date.fromisoformat(appt["date"]) - timedelta(days=days)).isoformat()
    return render_template(
        "appointments/detail.html",
        a=appt,
        tasks=appt.get("tasks", []),
        remind_on=remind_on,
        is_due=reminder_due(appt, today()),
        task_text=task_text,
        task_errors={"text": task_error} if task_error else {},
    ), status


def to_detail(appt_id, anchor=""):
    return redirect(url_for(".detail", appt_id=appt_id) + anchor)


@bp.get("/")
def index():
    return render_list()


@bp.post("/")
def create():
    data, errors = validate(request.form)
    if errors:
        return render_list(form=data, errors=errors, status=400)

    with storage.modify("appointments") as records:
        records.append({
            "id": storage.next_id(records),
            **data,
            "status": "scheduled",
            "reminder_dismissed": False,
            "tasks": [],
            "created_at": now_iso(),
        })
    flash(f"Added: {data['reason']} with {data['provider']}.", "success")
    return redirect(url_for(".index"))


@bp.get("/<int:appt_id>")
def detail(appt_id):
    return render_detail(find(storage.load("appointments"), appt_id))


@bp.get("/<int:appt_id>/edit")
def edit(appt_id):
    appt = find(storage.load("appointments"), appt_id)
    return render_template("appointments/edit.html", a=appt, form=appt, errors={})


@bp.post("/<int:appt_id>/edit")
def update(appt_id):
    data, errors = validate(request.form)
    if errors:
        appt = find(storage.load("appointments"), appt_id)
        return render_template("appointments/edit.html", a=appt, form=data, errors=errors), 400

    with storage.modify("appointments") as records:
        appt = find(records, appt_id)
        # A new date or reminder setting is a new reminder, so show it again.
        if (data["date"], data["reminder_days_before"]) != (appt["date"], appt.get("reminder_days_before")):
            appt["reminder_dismissed"] = False
        appt.update(data, updated_at=now_iso())
    flash("Changes saved.", "success")
    return to_detail(appt_id)


@bp.get("/<int:appt_id>/delete")
def confirm_delete(appt_id):
    appt = find(storage.load("appointments"), appt_id)
    return render_template("appointments/confirm_delete.html", a=appt)


@bp.post("/<int:appt_id>/delete")
def delete(appt_id):
    with storage.modify("appointments") as records:
        appt = find(records, appt_id)
        records.remove(appt)
    flash(f"Deleted: {appt['reason']} with {appt['provider']}.", "success")
    return redirect(url_for(".index"))


@bp.post("/<int:appt_id>/status")
def set_status(appt_id):
    status = request.form.get("status")
    if status not in STATUSES:
        abort(400, description="That status isn't one MedFlow knows.")
    with storage.modify("appointments") as records:
        find(records, appt_id)["status"] = status
    flash(f"Marked as {status}.", "success")
    return to_detail(appt_id)


@bp.post("/<int:appt_id>/reminder/dismiss")
def dismiss_reminder(appt_id):
    with storage.modify("appointments") as records:
        find(records, appt_id)["reminder_dismissed"] = True
    flash("Reminder dismissed.", "success")
    # Only two known destinations, so no open redirect.
    if request.form.get("next") == "list":
        return redirect(url_for(".index"))
    return to_detail(appt_id)


@bp.post("/<int:appt_id>/tasks")
def add_task(appt_id):
    text = request.form.get("text", "").strip()
    error = None
    if not text:
        error = "Enter a follow-up task."
    elif len(text) > TASK_MAX:
        error = f"Tasks must be {TASK_MAX} characters or fewer."
    if error:
        appt = find(storage.load("appointments"), appt_id)
        return render_detail(appt, task_text=text, task_error=error, status=400)

    with storage.modify("appointments") as records:
        tasks = find(records, appt_id).setdefault("tasks", [])
        tasks.append({"id": storage.next_id(tasks), "text": text, "done": False})
    flash("Follow-up task added.", "success")
    return to_detail(appt_id, "#tasks")


@bp.post("/<int:appt_id>/tasks/<int:task_id>/toggle")
def toggle_task(appt_id, task_id):
    with storage.modify("appointments") as records:
        task = find_task(find(records, appt_id), task_id)
        task["done"] = not task["done"]
    return to_detail(appt_id, "#tasks")


@bp.post("/<int:appt_id>/tasks/<int:task_id>/delete")
def delete_task(appt_id, task_id):
    with storage.modify("appointments") as records:
        appt = find(records, appt_id)
        appt["tasks"].remove(find_task(appt, task_id))
    flash("Follow-up task removed.", "success")
    return to_detail(appt_id, "#tasks")
