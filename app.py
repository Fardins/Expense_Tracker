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


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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
