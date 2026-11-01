import importlib
import os
import re
import sqlite3
from contextlib import closing

import pytest
from werkzeug.security import check_password_hash

from database import db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_ERROR = "All fields are required."
EMAIL_ERROR = "Please enter a valid email address."
PASSWORD_ERROR = "Password must be at least 8 characters."
DUPLICATE_ERROR = "An account with that email already exists."


def post(client, **overrides):
    data = {"name": "Test User", "email": "new@example.com", "password": "password123"}
    data.update(overrides)
    return client.post("/register", data=data)


def user_count():
    with closing(db.get_db()) as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ------------------------------------------------------------------ #
# Route                                                               #
# ------------------------------------------------------------------ #

def test_get_register_renders_form(client):
    res = client.get("/register")
    assert res.status_code == 200
    assert b"<form" in res.data
    assert b'class="auth-error"' not in res.data


def test_register_success_creates_user_and_redirects(client):
    assert user_count() == 1
    res = post(client)
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/login")
    assert user_count() == 2
    assert db.get_user_by_email("new@example.com")["name"] == "Test User"


def test_register_normalises_name_and_email(client):
    post(client, name="  Ann  ", email="  New@Example.COM ")
    user = db.get_user_by_email("new@example.com")
    assert user is not None
    assert user["name"] == "Ann"


def test_password_is_hashed(client):
    post(client)
    stored = db.get_user_by_email("new@example.com")["password_hash"]
    assert stored != "password123"
    assert check_password_hash(stored, "password123")
    assert not check_password_hash(stored, "wrong-password")


@pytest.mark.parametrize(
    "overrides",
    [{"name": ""}, {"email": ""}, {"password": ""}, {"name": "   "}],
)
def test_missing_field_errors(client, overrides):
    res = post(client, **overrides)
    assert res.status_code == 400
    assert REQUIRED_ERROR.encode() in res.data
    assert user_count() == 1


@pytest.mark.parametrize("email", ["plainaddress", "user@localhost", "user.name@"])
def test_invalid_email(client, email):
    res = post(client, email=email)
    assert res.status_code == 400
    assert EMAIL_ERROR.encode() in res.data
    assert user_count() == 1


def test_short_password(client):
    res = post(client, password="short7!")
    assert res.status_code == 400
    assert PASSWORD_ERROR.encode() in res.data
    assert user_count() == 1

    res = post(client, password="exactly8")
    assert res.status_code == 302


def test_validation_order(client):
    res = post(client, name="", email="bad", password="x")
    assert REQUIRED_ERROR.encode() in res.data
    res = post(client, email="bad", password="x")
    assert EMAIL_ERROR.encode() in res.data
    assert PASSWORD_ERROR.encode() not in res.data


@pytest.mark.parametrize("email", ["demo@spendly.com", " DEMO@Spendly.com "])
def test_duplicate_email(client, email):
    res = post(client, email=email)
    assert res.status_code == 409
    assert DUPLICATE_ERROR.encode() in res.data
    assert user_count() == 1


def test_duplicate_race_condition(client, monkeypatch):
    # Pre-check misses the existing user; the UNIQUE constraint must catch it.
    monkeypatch.setattr(importlib.import_module("app"), "get_user_by_email", lambda e: None)
    res = post(client, email="demo@spendly.com")
    assert res.status_code == 409
    assert DUPLICATE_ERROR.encode() in res.data
    assert user_count() == 1


def test_error_refills_name_and_email_not_password(client):
    res = post(client, name="Jane", email="jane@example.com", password="short")
    body = res.data.decode()
    assert 'value="Jane"' in body
    assert 'value="jane@example.com"' in body
    password_input = re.search(r'<input[^>]*type="password"[^>]*>', body).group(0)
    assert "value=" not in password_input
    assert "short" not in password_input


# ------------------------------------------------------------------ #
# Template and CSS                                                    #
# ------------------------------------------------------------------ #

def test_form_action_uses_url_for(client):
    with open(os.path.join(ROOT, "templates", "register.html"), encoding="utf-8") as f:
        source = f.read()
    assert 'action="/register"' not in source
    assert "url_for('register')" in source
    assert b'action="/register"' in client.get("/register").data


def test_password_minlength_attribute(client):
    body = client.get("/register").data.decode()
    password_input = re.search(r'<input[^>]*type="password"[^>]*>', body).group(0)
    assert 'minlength="8"' in password_input


def test_auth_error_css_uses_variables_only():
    with open(os.path.join(ROOT, "static", "css", "style.css"), encoding="utf-8") as f:
        css = f.read()
    block = re.search(r"\.auth-error\s*\{([^}]*)\}", css).group(1)
    assert "#" not in block
    assert "--danger-border:" in css


# ------------------------------------------------------------------ #
# DB helpers                                                          #
# ------------------------------------------------------------------ #

def test_get_user_by_email_helper(app):
    user = db.get_user_by_email("demo@spendly.com")
    assert isinstance(user, sqlite3.Row)
    assert user["name"] == "Demo User"
    assert db.get_user_by_email("nobody@example.com") is None


def test_create_user_helper(app):
    user_id = db.create_user("Helper", "helper@example.com", "password123")
    assert isinstance(user_id, int)
    assert db.get_user_by_email("helper@example.com")["id"] == user_id
    with pytest.raises(sqlite3.IntegrityError):
        db.create_user("Again", "helper@example.com", "password123")
