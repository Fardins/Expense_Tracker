import os
import sqlite3
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    get_category_totals,
    get_db,
    get_expense_summary,
    get_recent_expenses,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
# Dev-only fallback — set SECRET_KEY in the environment for any real deployment.
app.secret_key = os.environ.get("SECRET_KEY") or "dev-only-insecure-secret-change-me"

with app.app_context():
    init_db()
    seed_db()


DUPLICATE_EMAIL_ERROR = "An account with that email already exists."
LOGIN_REQUIRED_ERROR = "Email and password are required."
INVALID_LOGIN_ERROR = "Invalid email or password."


def _registration_error(name, email, password):
    """Return the first validation error message, or None if input is valid."""
    if not name or not email or not password:
        return "All fields are required."
    at = email.find("@")
    if at == -1 or "." not in email[at + 1:]:
        return "Please enter a valid email address."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    return None


def _format_month(created_at):
    """'YYYY-MM-DD HH:MM:SS' -> 'Month YYYY' ('' if missing)."""
    if not created_at:
        return ""
    return datetime.strptime(created_at[:10], "%Y-%m-%d").strftime("%B %Y")


def _build_user(row):
    """Shape a users row into the profile card context."""
    name = row["name"]
    return {
        "name": name,
        "initial": name[:1].upper() or "?",
        "email": row["email"],
        "member_since": _format_month(row["created_at"]),
    }


def _format_date(iso):
    """'YYYY-MM-DD' -> 'DD Mon YYYY'."""
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d %b %Y")


def _build_transactions(user_id):
    """-> [{'date': 'DD Mon YYYY', 'description': str, 'category': str, 'amount': float}]"""
    return [
        {
            "date": _format_date(row["date"]),
            "description": row["description"] or "",
            "category": row["category"],
            "amount": float(row["amount"]),
        }
        for row in get_recent_expenses(user_id)
    ]


def _build_stats(user_id, categories):
    """-> {'total_spent': float, 'transaction_count': int, 'top_category': str | None}

    ``categories`` is _build_categories output: sorted by amount DESC, name ASC.
    """
    summary = get_expense_summary(user_id)
    return {
        "total_spent": round(summary["total"], 2),
        "transaction_count": summary["count"],
        "top_category": categories[0]["name"] if categories else None,
    }


def _category_pcts(rows):
    """(category, amount) rows -> [{'name', 'amount', 'pct'}]; [] if total is 0."""
    total = sum(row[1] for row in rows)
    if not rows or total == 0:
        return []
    return [
        {
            "name": row[0],
            "amount": round(row[1], 2),
            "pct": round(row[1] / total * 100, 1),
        }
        for row in rows
    ]


def _build_categories(user_id):
    """-> [{'name': str, 'amount': float, 'pct': float (1dp)}], [] when no spend."""
    return _category_pcts(get_category_totals(user_id))


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = _registration_error(name, email, password)
    status = 400
    if error is None and get_user_by_email(email) is not None:
        error, status = DUPLICATE_EMAIL_ERROR, 409
    if error is None:
        try:
            create_user(name, email, password)
        except sqlite3.IntegrityError:  # email taken between check and insert
            error, status = DUPLICATE_EMAIL_ERROR, 409

    if error is not None:
        return render_template(
            "register.html", error=error, name=name, email=email
        ), status
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("profile"))
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")  # never strip passwords

    if not email or not password:
        return render_template(
            "login.html", error=LOGIN_REQUIRED_ERROR, email=email
        ), 400

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html", error=INVALID_LOGIN_ERROR, email=email
        ), 401

    session.clear()  # drop any pre-login session data (fixation guard)
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    row = get_user_by_id(user_id)
    if row is None:  # stale session pointing at a deleted user
        session.clear()
        return redirect(url_for("login"))

    categories = _build_categories(user_id)
    return render_template(
        "profile.html",
        user=_build_user(row),
        stats=_build_stats(user_id, categories),
        transactions=_build_transactions(user_id),
        categories=categories,
    )


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
