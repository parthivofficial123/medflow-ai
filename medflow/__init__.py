import io
import logging
import os
import secrets
from datetime import datetime
from urllib.parse import urlsplit

import click
from flask import Flask, Request, abort, redirect, render_template, request, session, url_for
from werkzeug.exceptions import InternalServerError, RequestEntityTooLarge, ServiceUnavailable
from werkzeug.middleware.proxy_fix import ProxyFix

from . import storage

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
DEV_SECRET = "dev-only-not-a-secret"
log = logging.getLogger(__name__)


class MemoryUploadRequest(Request):
    # Werkzeug writes uploads over 500 KB to a temporary file. Uploaded bills must never
    # touch disk, so every upload goes to memory; MAX_CONTENT_LENGTH caps its size.
    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        return io.BytesIO()


def create_app(test_config=None):
    # Imported here because the feature modules import this package (e.g. the money filter).
    from . import appointments, auth, bills, expenses

    # Static files live in public/ because Vercel serves that folder itself.
    app = Flask(__name__, instance_relative_config=True, static_folder="../public/static")
    app.request_class = MemoryUploadRequest
    app.config.from_mapping(
        # The fallback only exists so a local demo starts without setup.
        SECRET_KEY=os.environ.get("MEDFLOW_SECRET_KEY", DEV_SECRET),
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=bills.MAX_UPLOAD_BYTES,
        DATA_DIR=app.instance_path,
        SEED_DIR=os.path.join(os.path.dirname(app.root_path), "data", "seed"),
        STORAGE=os.environ.get("MEDFLOW_STORAGE", "json"),
        SUPABASE_URL=os.environ.get("SUPABASE_URL", ""),
        SUPABASE_PUBLISHABLE_KEY=os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""),
        ON_VERCEL=os.environ.get("VERCEL") == "1",
    )
    if test_config:
        app.config.update(test_config)
    check_config(app.config)

    if app.config["ON_VERCEL"]:
        # Vercel's proxy terminates HTTPS; trust its headers so sign-in redirects use https.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
        app.config["SESSION_COOKIE_SECURE"] = True
    if app.config["STORAGE"] == "json":
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
        signed_in = app.config["STORAGE"] == "json" or bool(session.get("access_token"))
        return {"csrf_token": csrf_token, "signed_in": signed_in}

    app.add_template_filter(to_date)
    app.add_template_filter(fmt_date)
    app.add_template_filter(fmt_time)
    app.add_template_filter(money)

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(405)
    def http_error(e):
        return render_template("error.html", error=e), e.code

    @app.errorhandler(413)
    def too_large(e):
        e = RequestEntityTooLarge(description="That file is larger than 4 MB. Upload a smaller copy of the bill.")
        return render_template("error.html", error=e), 413

    @app.errorhandler(storage.DatabaseError)
    def database_error(e):
        log.error("Database request failed: %s", e)
        message = ("MedFlow couldn't reach its database, so your last change may not have been "
                   "saved. Reload the page to check, then try again.")
        return render_template("error.html", error=ServiceUnavailable(description=message)), 503

    # Only used without --debug; in debug mode Flask shows its debugger instead.
    # The exception itself is already in the server log; the page never shows it.
    @app.errorhandler(500)
    def server_error(e):
        if isinstance(getattr(e, "original_exception", None), storage.StorageError):
            message = (
                f"MedFlow's {e.original_exception.collection} data file is damaged, so nothing was "
                "changed. Stop the server and run 'flask --app medflow reset-demo' to restore the "
                "demo data. This replaces any changes you made."
            )
        else:
            message = "Something went wrong on our side. Try again; if it keeps happening, check the terminal running MedFlow."
        return render_template("error.html", error=InternalServerError(description=message)), 500

    app.register_blueprint(auth.bp)
    app.register_blueprint(appointments.bp)
    app.register_blueprint(expenses.bp)
    app.register_blueprint(bills.bp)

    @app.get("/")
    def index():
        return redirect(url_for("appointments.index"))

    @app.cli.command("reset-demo")
    @click.confirmation_option(
        prompt="This REPLACES all MedFlow data (appointments, tasks, reminders and any changes "
               "you made) with the fictional demo data. It can't be undone. Continue?"
    )
    def reset_demo():
        """Replace all user data with the fictional demo data in data/seed/."""
        if app.config["STORAGE"] != "json":
            raise click.ClickException("With Supabase, each user resets their own data from "
                                       "the 'Reset my demo data' link in the app.")
        storage.reset()
        click.echo(f"Demo data restored in {app.config['DATA_DIR']}")

    return app


def check_config(config):
    """Refuse to start with a missing or unsafe setting. Messages never include values."""
    if config["STORAGE"] not in ("json", "supabase"):
        raise RuntimeError("MEDFLOW_STORAGE must be 'json' or 'supabase'.")
    if config["ON_VERCEL"] and config["STORAGE"] != "supabase":
        raise RuntimeError("On Vercel, MEDFLOW_STORAGE must be 'supabase'; there is no JSON fallback.")
    if config["STORAGE"] != "supabase":
        return
    url = urlsplit(config["SUPABASE_URL"])
    if url.scheme not in ("http", "https") or not url.netloc:
        raise RuntimeError("SUPABASE_URL must be your project URL, like https://<ref>.supabase.co")
    # Only the origin: a pasted ".../rest/v1/" would otherwise break every request.
    config["SUPABASE_URL"] = f"{url.scheme}://{url.netloc}"
    key = config["SUPABASE_PUBLISHABLE_KEY"]
    if not key:
        raise RuntimeError("SUPABASE_PUBLISHABLE_KEY isn't set.")
    if key.startswith("sb_secret_"):
        raise RuntimeError("SUPABASE_PUBLISHABLE_KEY holds a secret key. MedFlow only uses the "
                           "publishable key; keep the secret key out of the app.")
    if config["SECRET_KEY"] in ("", DEV_SECRET):
        raise RuntimeError("Set MEDFLOW_SECRET_KEY: sign-in sessions need a real secret.")


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def to_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def fmt_date(value):
    d = to_date(value)
    return f"{d:%a, %b} {d.day}, {d.year}"


def money(cents, signed=False):
    """Integer cents -> "$1,234.56"; None -> an em dash. Integer math only, no floats."""
    if cents is None:
        return "—"
    sign = "-" if cents < 0 else ("+" if signed and cents > 0 else "")
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rest:02d}"


def fmt_time(value):
    t = datetime.strptime(value, "%H:%M")
    return f"{t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"
