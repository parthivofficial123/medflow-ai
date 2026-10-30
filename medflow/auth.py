"""Google Sign-In through Supabase Auth (PKCE), and the sign-in guard for Supabase mode.

The session cookie (signed, HttpOnly) holds only the access token, its expiry and
the user's email. The refresh token is dropped right after sign-in, so a stolen
cookie stops working when the access token expires; the user then signs in again.
Tokens never appear in URLs, templates or logs.
"""

import base64
import hashlib
import logging
import secrets
import time
from urllib.parse import urlencode

import httpx
from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request,
                   session, url_for)
from supabase import ClientOptions, create_client
from supabase_auth.errors import AuthError

from . import storage

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)

PUBLIC_ENDPOINTS = {"index", "welcome", "auth.login", "auth.start", "auth.callback", "auth.logout", "static"}
# Treat a token this close to expiry as expired, so it can't run out mid-request.
EXPIRY_MARGIN_SECONDS = 60


def supabase_mode():
    return current_app.config["STORAGE"] == "supabase"


def anonymous_client():
    return create_client(
        current_app.config["SUPABASE_URL"],
        current_app.config["SUPABASE_PUBLISHABLE_KEY"],
        ClientOptions(auto_refresh_token=False, persist_session=False, flow_type="pkce"),
    )


def code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def safe_next(path):
    """Only a path on this site. "//host", backslashes and control characters (browsers drop
    tabs and newlines, so "/\\t/host" becomes "//host") would leave it."""
    if (path and path.startswith("/") and not path.startswith("//") and "\\" not in path
            and all(" " < c != "\x7f" for c in path)):
        return path
    return url_for("index")


def end_session():
    for key in ("access_token", "expires_at", "email"):
        session.pop(key, None)


@bp.before_app_request
def require_sign_in():
    if not supabase_mode() or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    token = session.get("access_token")
    if token and session.get("expires_at", 0) - EXPIRY_MARGIN_SECONDS > time.time():
        g.access_token = token
        return None
    if token:
        end_session()
        flash("Your session ended. Sign in again to continue.", "warning")
    # Only real pages: the browser's own /favicon.ico request would otherwise replace it.
    if request.method == "GET" and request.endpoint is not None:
        session["next"] = request.full_path.rstrip("?")
    return redirect(url_for("auth.login"))


@bp.app_errorhandler(storage.SignedOut)
def signed_out(e):
    end_session()
    flash("Your session ended. Sign in again to continue.", "warning")
    return redirect(url_for("auth.login"))


@bp.get("/login")
def login():
    if not supabase_mode() or session.get("access_token"):
        return redirect(url_for("index"))
    return render_template("auth/login.html")


@bp.post("/login")
def start():
    if not supabase_mode():
        return redirect(url_for("index"))
    verifier = secrets.token_urlsafe(64)
    session["pkce_verifier"] = verifier
    query = urlencode({
        "provider": "google",
        "redirect_to": url_for("auth.callback", _external=True),
        "code_challenge": code_challenge(verifier),
        "code_challenge_method": "s256",
    })
    return redirect(f"{current_app.config['SUPABASE_URL']}/auth/v1/authorize?{query}")


@bp.get("/auth/callback")
def callback():
    if not supabase_mode():
        return redirect(url_for("index"))
    verifier = session.pop("pkce_verifier", None)
    code = request.args.get("code")
    if not verifier or not code:
        flash("Sign-in didn't finish. Try again.", "error")
        return redirect(url_for("auth.login"))
    try:
        result = anonymous_client().auth.exchange_code_for_session(
            {"auth_code": code, "code_verifier": verifier})
    except (AuthError, httpx.HTTPError) as e:
        log.warning("Sign-in code exchange failed: %s", type(e).__name__)
        flash("Sign-in didn't finish. Try again.", "error")
        return redirect(url_for("auth.login"))

    next_path = session.get("next")
    # A fresh session on sign-in, so nothing set before it (a planted cookie) carries over.
    session.clear()
    session["access_token"] = result.session.access_token
    session["expires_at"] = result.session.expires_at
    session["email"] = result.user.email
    g.access_token = result.session.access_token
    if storage.seed_if_empty():
        flash("Welcome! Your account starts with fictional demo data to explore.", "success")
    return redirect(safe_next(next_path))


@bp.post("/logout")
def logout():
    token = session.get("access_token")
    if supabase_mode() and token:
        try:
            anonymous_client().auth.admin.sign_out(token, "local")
        except (AuthError, httpx.HTTPError) as e:
            # The token may already have expired; the cookie is cleared either way.
            log.info("Supabase sign-out failed: %s", type(e).__name__)
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("auth.login") if supabase_mode() else url_for("index"))


def demo_reset_allowed():
    return not supabase_mode() or current_app.config["DEMO_RESET"]


@bp.get("/account/reset")
def confirm_reset():
    if not demo_reset_allowed():
        abort(404)
    return render_template("auth/confirm_reset.html")


@bp.post("/account/reset")
def reset():
    if not demo_reset_allowed():
        abort(404)
    if request.form.get("confirmed") != "yes":
        return redirect(url_for(".confirm_reset"))
    storage.reset()
    flash("Your data was replaced with the fictional demo data.", "success")
    return redirect(url_for("index"))
