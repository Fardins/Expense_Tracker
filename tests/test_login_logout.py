import os
import re

import pytest

from database import db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_ERROR = b"Email and password are required."
INVALID_ERROR = b"Invalid email or password."


def login(client, email="demo@spendly.com", password="demo123"):
    return client.post("/login", data={"email": email, "password": password})


def session_data(client):
    with client.session_transaction() as s:
        return dict(s)


def navbar(res):
    return re.search(r'<nav class="navbar">.*?</nav>', res.data.decode(), re.S).group(0)


# ------------------------------------------------------------------ #
# Login                                                               #
# ------------------------------------------------------------------ #

def test_get_login_renders_form(client):
    res = client.get("/login")
    assert res.status_code == 200
    assert b"<form" in res.data
    assert b'class="auth-error"' not in res.data


def test_demo_login_redirects_and_sets_session(client):
    res = login(client)
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/profile")
    data = session_data(client)
    assert data["user_id"] == db.get_user_by_email("demo@spendly.com")["id"]
    assert data["user_name"] == "Demo User"


def test_login_normalises_email(client):
    res = login(client, email=" DEMO@Spendly.com ")
    assert res.status_code == 302
    assert "user_id" in session_data(client)


def test_registered_user_can_log_in(client):
    client.post(
        "/register",
        data={"name": "New User", "email": "new@example.com", "password": "password123"},
    )
    res = login(client, email="new@example.com", password="password123")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/profile")
    assert session_data(client)["user_name"] == "New User"


def test_wrong_password(client):
    res = login(client, password="wrong-password")
    assert res.status_code == 401
    assert INVALID_ERROR in res.data
    assert "user_id" not in session_data(client)


def test_unknown_email_same_message(client):
    unknown = login(client, email="nobody@example.com")
    wrong = login(client, password="wrong-password")
    assert unknown.status_code == wrong.status_code == 401
    assert INVALID_ERROR in unknown.data
    error_div = r'<div class="auth-error">(.*?)</div>'
    assert (
        re.search(error_div, unknown.data.decode()).group(1)
        == re.search(error_div, wrong.data.decode()).group(1)
    )
    assert "user_id" not in session_data(client)


@pytest.mark.parametrize(
    "overrides", [{"email": ""}, {"password": ""}, {"email": "   "}]
)
def test_empty_fields(client, overrides):
    res = login(client, **overrides)
    assert res.status_code == 400
    assert REQUIRED_ERROR in res.data
    assert "user_id" not in session_data(client)


def test_no_minimum_length_on_login(client):
    # demo123 is 7 chars — login must not apply the registration rule.
    assert login(client).status_code == 302


def test_password_not_stripped(client):
    res = login(client, password=" demo123 ")
    assert res.status_code == 401
    assert "user_id" not in session_data(client)


def test_failed_login_refills_email_not_password(client):
    body = login(client, password="wrong-password").data.decode()
    assert 'value="demo@spendly.com"' in body
    password_input = re.search(r'<input[^>]*type="password"[^>]*>', body).group(0)
    assert "value=" not in password_input


def test_login_clears_preexisting_session(client):
    with client.session_transaction() as s:
        s["stale"] = "value"
    login(client)
    data = session_data(client)
    assert "stale" not in data
    assert "user_id" in data


def test_get_login_when_logged_in_redirects(client):
    login(client)
    res = client.get("/login")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/profile")


# ------------------------------------------------------------------ #
# Navbar                                                              #
# ------------------------------------------------------------------ #

def test_navbar_logged_out(client):
    nav = navbar(client.get("/"))
    assert "Sign in" in nav
    assert "Get started" in nav
    assert "Sign out" not in nav


def test_navbar_logged_in(client):
    login(client)
    nav = navbar(client.get("/"))
    assert "Demo User" in nav
    assert "Sign out" in nav
    assert 'href="/logout"' in nav
    assert "Sign in" not in nav
    assert "Get started" not in nav


def test_sign_out_link_visible_on_mobile(client):
    # style.css hides non-.nav-cta nav links at narrow widths.
    login(client)
    link = re.search(r'<a[^>]*href="/logout"[^>]*>', navbar(client.get("/"))).group(0)
    assert "nav-cta" in link


# ------------------------------------------------------------------ #
# Logout                                                              #
# ------------------------------------------------------------------ #

def test_logout_clears_session(client):
    login(client)
    res = client.get("/logout")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/")
    assert session_data(client) == {}
    nav = navbar(client.get("/"))
    assert "Sign in" in nav
    assert "Sign out" not in nav


def test_logout_when_logged_out(client):
    res = client.get("/logout")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/")


# ------------------------------------------------------------------ #
# Template and CSS                                                    #
# ------------------------------------------------------------------ #

def test_login_form_action_uses_url_for(client):
    with open(os.path.join(ROOT, "templates", "login.html"), encoding="utf-8") as f:
        source = f.read()
    assert 'action="/login"' not in source
    assert "url_for('login')" in source
    assert b'action="/login"' in client.get("/login").data


def test_nav_user_css_uses_variables_only():
    with open(os.path.join(ROOT, "static", "css", "style.css"), encoding="utf-8") as f:
        css = f.read()
    block = re.search(r"\.nav-user\s*\{([^}]*)\}", css).group(1)
    assert "#" not in block
