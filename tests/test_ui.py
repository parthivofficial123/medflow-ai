"""The landing page, and smoke tests that every page stays compatible with the CSP and motion rules."""

import re
from pathlib import Path

import pytest

from tests.conftest import get_csrf_token, sign_in

CSS = Path(__file__).parent.parent / "public" / "static" / "css" / "app.css"


# Landing page

def test_signed_out_visitors_see_the_landing_page(sb_app):
    response = sb_app.test_client().get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Medical bills, made&nbsp;simpler." in html
    assert 'aria-label="Main"' not in html


def test_get_started_uses_the_existing_google_sign_in(sb_app, fake_db):
    client = sb_app.test_client()
    html = client.get("/").get_data(as_text=True)
    assert re.search(r'<form class="landing__cta-form" method="post" action="/login">\s*'
                     r'<input type="hidden" name="csrf_token"', html)
    response = client.post("/login", data={"csrf_token": get_csrf_token(client, "/")})
    assert response.headers["Location"].startswith("https://demo-ref.supabase.co/auth/v1/authorize?")


def test_signed_in_users_go_straight_to_the_app(sb_app, fake_db):
    client = sign_in(sb_app, fake_db)
    assert client.get("/").headers["Location"] == "/appointments/"
    html = client.get("/welcome").get_data(as_text=True)
    assert "Open MedFlow" in html and "Continue with Google" not in html


def test_welcome_is_public_and_json_mode_keeps_its_redirect(sb_app, client):
    assert sb_app.test_client().get("/welcome").status_code == 200
    assert client.get("/").headers["Location"] == "/appointments/"
    assert "Open MedFlow" in client.get("/welcome").get_data(as_text=True)


def test_landing_states_its_limits_and_claims_nothing_it_cannot_back(sb_app):
    html = sb_app.test_client().get("/").get_data(as_text=True)
    for limit in ("student prototype", "hasn't been reviewed against HIPAA", "Fictional bills only",
                  "not medical, billing or insurance advice", "fictional bill"):
        assert limit in html
    for claim in ("HIPAA compliant", "HIPAA-compliant", "bank-level", "medical-grade", "guarantee"):
        assert claim not in html


def test_signed_out_pages_offer_sign_in(sb_app):
    client = sb_app.test_client()
    assert 'href="/login">Sign in</a>' in client.get("/").get_data(as_text=True)
    login = client.get("/login").get_data(as_text=True)
    assert 'href="/login">Sign in</a>' not in login
    assert 'href="/">What is MedFlow?</a>' in login


# Every page works under the CSP (default-src 'self': no inline styles or scripts)

PAGES = ["/welcome", "/appointments/", "/appointments/1", "/appointments/1/edit", "/expenses/",
         "/expenses/1/edit", "/bills/", "/account/reset"]


@pytest.mark.parametrize("path", PAGES)
def test_pages_have_no_inline_styles_or_scripts(client, path):
    response = client.get(path)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert not re.search(r"\sstyle=", html)
    assert re.findall(r"<script\b[^>]*>", html) == ['<script src="/static/js/app.js" defer>']


# Motion

def test_every_animation_is_opt_in_and_reduced_motion_turns_all_off():
    css = CSS.read_text(encoding="utf-8")
    opt_in = css.index("@media (prefers-reduced-motion: no-preference)")
    reduce = css.index("@media (prefers-reduced-motion: reduce)")
    # The final state is the default: no element is hidden waiting for an animation.
    assert "animation:" not in css[:opt_in]
    assert opt_in < reduce and "@media" not in css[reduce + 1:]
    assert "animation: none !important" in css[reduce:] and "transition: none !important" in css[reduce:]


def test_css_loads_nothing_from_other_sites():
    css = CSS.read_text(encoding="utf-8")
    assert "url(" not in css and "@import" not in css
