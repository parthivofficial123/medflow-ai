import os
import secrets
from datetime import datetime

import click
from flask import Flask, abort, redirect, render_template, request, session, url_for

from . import storage

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        # The fallback only exists so a local demo starts without setup.
        SECRET_KEY=os.environ.get("MEDFLOW_SECRET_KEY", "dev-only-not-a-secret"),
        SESSION_COOKIE_SAMESITE="Lax",
        DATA_DIR=app.instance_path,
        SEED_DIR=os.path.join(os.path.dirname(app.root_path), "data", "seed"),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.config["DATA_DIR"], exist_ok=True)
    with app.app_context():
        storage.seed_missing()

    @app.before_request
    def check_csrf():
        if request.method not in UNSAFE_METHODS:
            return
        expected = session.get("csrf_token")
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        if not expected or not sent or not secrets.compare_digest(expected, sent):
            abort(400, description="This form expired or was not sent from MedFlow. "
                                   "Go back, reload the page, and try again.")

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": csrf_token}

    app.add_template_filter(to_date)
    app.add_template_filter(fmt_date)
    app.add_template_filter(fmt_time)

    @app.errorhandler(400)
    @app.errorhandler(404)
    def http_error(e):
        return render_template("error.html", error=e), e.code

    from . import appointments
    app.register_blueprint(appointments.bp)

    @app.get("/")
    def index():
        return redirect(url_for("appointments.index"))

    @app.cli.command("reset-demo")
    def reset_demo():
        """Restore all user data from data/seed/ (fictional demo data)."""
        storage.reset()
        click.echo(f"Demo data restored in {app.config['DATA_DIR']}")

    return app


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def to_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def fmt_date(value):
    d = to_date(value)
    return f"{d:%a, %b} {d.day}, {d.year}"


def fmt_time(value):
    t = datetime.strptime(value, "%H:%M")
    return f"{t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"
