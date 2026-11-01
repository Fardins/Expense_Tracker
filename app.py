import os
import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db

app = Flask(__name__)
# Dev-only fallback — set SECRET_KEY in the environment for any real deployment.
app.secret_key = os.environ.get("SECRET_KEY") or "dev-only-insecure-secret-change-me"

with app.app_context():
    init_db()
    seed_db()


DUPLICATE_EMAIL_ERROR = "An account with that email already exists."
LOGIN_REQUIRED_ERROR = "Email and password are required."
INVALID_LOGIN_ERROR = "Invalid email or password."

# Step 4 placeholder profile data — replaced by real DB queries in a later step.
PLACEHOLDER_EMAIL = "demo@spendly.com"
PLACEHOLDER_MEMBER_SINCE = "January 2026"
PLACEHOLDER_TRANSACTION_COUNT = 18
PLACEHOLDER_TRANSACTIONS = [
    {"date": "31 Oct 2026", "description": "Weekly groceries", "category": "Food", "amount": 1240.00},
    {"date": "29 Oct 2026", "description": "Electricity bill", "category": "Bills", "amount": 1850.00},
    {"date": "27 Oct 2026", "description": "Metro card top-up", "category": "Transport", "amount": 500.00},
    {"date": "24 Oct 2026", "description": "Pharmacy", "category": "Health", "amount": 420.00},
    {"date": "21 Oct 2026", "description": "Movie tickets", "category": "Entertainment", "amount": 650.00},
    {"date": "18 Oct 2026", "description": "Running shoes", "category": "Shopping", "amount": 1475.50},
]
# Sorted by amount, descending; sums to 12650.00.
PLACEHOLDER_CATEGORY_AMOUNTS = [
    ("Food", 4250.00),
    ("Bills", 3200.00),
    ("Transport", 1850.00),
    ("Shopping", 1475.50),
    ("Health", 900.00),
    ("Entertainment", 650.00),
    ("Other", 324.50),
]


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
    if not session.get("user_id"):
        return redirect(url_for("login"))

    name = session.get("user_name", "")
    total = sum(amount for _, amount in PLACEHOLDER_CATEGORY_AMOUNTS)
    categories = [
        {"name": cat, "amount": amount, "pct": round(amount / total * 100, 1)}
        for cat, amount in PLACEHOLDER_CATEGORY_AMOUNTS
    ]
    user = {
        "name": name,
        "initial": name[:1].upper() or "?",
        "email": PLACEHOLDER_EMAIL,
        "member_since": PLACEHOLDER_MEMBER_SINCE,
    }
    stats = {
        "total_spent": total,
        "transaction_count": PLACEHOLDER_TRANSACTION_COUNT,
        "top_category": categories[0]["name"],
    }
    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=PLACEHOLDER_TRANSACTIONS,
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
