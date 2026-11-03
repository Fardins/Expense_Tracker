import hmac
import math
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    CATEGORIES,
    create_expense,
    create_user,
    delete_expense_row,
    get_category_totals,
    get_db,
    get_expense_by_id,
    get_expense_summary,
    get_recent_expenses,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
    update_expense,
)

app = Flask(__name__)
# Dev-only fallback — set SECRET_KEY in the environment for any real deployment.
app.secret_key = os.environ.get("SECRET_KEY") or "dev-only-insecure-secret-change-me"
app.config.update(
    # Cross-site POSTs don't carry the session cookie (CSRF mitigation). The
    # edit and delete forms also carry a per-session token (_csrf_token); the
    # add form gets one in a follow-up.
    SESSION_COOKIE_SAMESITE="Lax",
    # Forms here are tiny; reject oversized bodies before they are parsed.
    MAX_CONTENT_LENGTH=16 * 1024,
)

with app.app_context():
    init_db()
    seed_db()


DUPLICATE_EMAIL_ERROR = "An account with that email already exists."
LOGIN_REQUIRED_ERROR = "Email and password are required."
INVALID_LOGIN_ERROR = "Invalid email or password."
INVALID_DATE_ERROR = "Invalid date — showing all time."
DATE_ORDER_ERROR = "Start date must be on or before end date."
AMOUNT_ERROR = "Enter an amount greater than 0."
AMOUNT_TOO_LARGE_ERROR = "Amount is too large."
CATEGORY_ERROR = "Choose a valid category."
EXPENSE_DATE_ERROR = "Enter a valid date."
FUTURE_DATE_ERROR = "Date cannot be in the future."
DESCRIPTION_LENGTH_ERROR = "Description must be 200 characters or fewer."

# Expense form limits
MAX_AMOUNT = 1_000_000
MAX_DESCRIPTION = 200
EXPENSE_FIELDS = ("amount", "category", "date", "description")


def _registration_error(name, email, password):
    """Return the first validation error message, or None if input is valid."""
    if not name or not email or not password:
        return "All fields are required."
    at = email.find("@")
    if at == -1 or "." not in email[at + 1 :]:
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


def _parse_iso_date(value):
    """'YYYY-MM-DD' -> normalised ISO str; blank -> None; ValueError if bad."""
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def _parse_date_filter(args):
    """request.args-like mapping -> {'date_from', 'date_to', 'error'}.

    Any invalid value, or from > to, drops both bounds (all time) with an error.
    """
    try:
        date_from = _parse_iso_date(args.get("from"))
        date_to = _parse_iso_date(args.get("to"))
    except ValueError:
        return {"date_from": None, "date_to": None, "error": INVALID_DATE_ERROR}
    if date_from and date_to and date_from > date_to:
        return {"date_from": None, "date_to": None, "error": DATE_ORDER_ERROR}
    return {"date_from": date_from, "date_to": date_to, "error": None}


def _parse_amount(raw):
    """Amount string -> (float rounded to 2dp, None) or (None, error).

    float() also accepts forms like '1e2' and '1_0'; that's fine because the
    range checks below still apply. round() passes nan/inf through unchanged,
    so the isfinite() check after it is safe. Rounding happens first so that
    e.g. '0.001' is rejected rather than stored as 0.00.
    """
    try:
        amount = round(float(raw), 2)
    except ValueError:
        return None, AMOUNT_ERROR
    if not math.isfinite(amount) or amount <= 0:
        return None, AMOUNT_ERROR
    if amount > MAX_AMOUNT:
        return None, AMOUNT_TOO_LARGE_ERROR
    return amount, None


def _parse_expense_form(form, today):
    """Form mapping -> (values, None) or (None, error). No SQL; first error wins.

    ``values`` is {'amount', 'category', 'date', 'description'} ready for
    create_expense(); ``today`` is a date, passed in so tests can control it.
    """
    amount, error = _parse_amount((form.get("amount") or "").strip())
    if error:
        return None, error

    category = form.get("category") or ""  # exact match, never stripped
    if category not in CATEGORIES:
        return None, CATEGORY_ERROR

    # _parse_iso_date returns None for a blank value and raises ValueError for
    # a malformed one; both mean "no valid date" here.
    try:
        expense_date = _parse_iso_date(form.get("date"))
    except ValueError:
        expense_date = None
    if expense_date is None:
        return None, EXPENSE_DATE_ERROR
    # Both sides are normalised 'YYYY-MM-DD', so string order == date order.
    if expense_date > today.isoformat():
        return None, FUTURE_DATE_ERROR

    description = (form.get("description") or "").strip()
    if len(description) > MAX_DESCRIPTION:
        return None, DESCRIPTION_LENGTH_ERROR

    return {
        "amount": amount,
        "category": category,
        "date": expense_date,
        "description": description or None,
    }, None


def _default_expense_values(today):
    """Initial form values for a new expense: today's date, first category."""
    return {
        "amount": "",
        "category": CATEGORIES[0],
        "date": today.isoformat(),
        "description": "",
    }


def _expense_form_values(form):
    """Submitted strings, stripped, for re-rendering the form (sticky values)."""
    return {field: (form.get(field) or "").strip() for field in EXPENSE_FIELDS}


def _session_user():
    """Logged-in users row, or None. Clears a session whose user is gone."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    row = get_user_by_id(user_id)
    if row is None:
        session.clear()
    return row


def _render_add_expense(form_values, today, error=None):
    """Render the add-expense form with the given values and optional error."""
    return render_template(
        "add_expense.html",
        form_values=form_values,
        categories=CATEGORIES,
        today=today.isoformat(),
        error=error,
    )


def _expense_row_values(row):
    """Expense DB row -> form_values for pre-filling the edit form."""
    return {
        "amount": f"{row['amount']:.2f}",
        "category": row["category"],
        "date": row["date"],
        "description": row["description"] or "",
    }


def _csrf_token():
    """The session's CSRF token, minted on first use."""
    token = session.get("csrf_token")
    if not token:
        token = session["csrf_token"] = secrets.token_urlsafe(32)
    return token


def _csrf_valid(form):
    """True if the submitted token matches the session token.

    Compared as bytes so non-ASCII input can't make compare_digest raise.
    """
    expected = session.get("csrf_token", "")
    submitted = form.get("csrf_token", "")
    return bool(expected) and hmac.compare_digest(submitted.encode(), expected.encode())


def _render_edit_expense(expense_id, form_values, today, error=None):
    """Render the edit-expense form with the given values and optional error."""
    return render_template(
        "edit_expense.html",
        expense_id=expense_id,
        form_values=form_values,
        categories=CATEGORIES,
        today=today.isoformat(),
        error=error,
        csrf_token=_csrf_token(),
    )


def _expense_summary(row):
    """Expense DB row -> display values for the delete confirmation page."""
    return {
        "date": _format_date(row["date"]),
        "description": row["description"] or row["category"],
        "category": row["category"],
        "amount": float(row["amount"]),
    }


def _render_delete_expense(expense_id, expense):
    """Render the delete confirmation page for one expense row."""
    return render_template(
        "delete_expense.html",
        expense_id=expense_id,
        expense=_expense_summary(expense),
        csrf_token=_csrf_token(),
    )


def _month_start(today, months_back):
    """1st of the month ``months_back`` months before ``today``'s month."""
    year, month0 = divmod(today.year * 12 + today.month - 1 - months_back, 12)
    return date(year, month0 + 1, 1)


def _preset(label, start=None, end=None):
    """One preset: ISO bounds (None = unbounded) plus its url_for query params."""
    params = {key: value for key, value in (("from", start), ("to", end)) if value}
    return {"label": label, "from": start, "to": end, "params": params}


def _date_presets(today):
    """-> [{'label', 'from', 'to', 'params'}] for the filter bar."""
    this_start = _month_start(today, 0)
    last_month_end = this_start - timedelta(days=1)
    return [
        _preset("All time"),
        _preset("This month", this_start.isoformat(), today.isoformat()),
        _preset(
            "Last month",
            _month_start(today, 1).isoformat(),
            last_month_end.isoformat(),
        ),
        _preset(
            "Last 3 months",
            _month_start(today, 2).isoformat(),
            today.isoformat(),
        ),
    ]


def _range_caption(date_from, date_to):
    """Human-readable description of the active range."""
    if date_from and date_to:
        return f"Showing {_format_date(date_from)} – {_format_date(date_to)}"
    if date_from:
        return f"Showing from {_format_date(date_from)}"
    if date_to:
        return f"Showing up to {_format_date(date_to)}"
    return "Showing all time"


def _build_filter(parsed, today):
    """Template context for the date filter bar."""
    date_from, date_to = parsed["date_from"], parsed["date_to"]
    presets = _date_presets(today)
    active_preset = next(
        (p["label"] for p in presets if (p["from"], p["to"]) == (date_from, date_to)),
        None,
    )
    return {
        "date_from": date_from,
        "date_to": date_to,
        "error": parsed["error"],
        "active": bool(date_from or date_to),
        "presets": presets,
        "active_preset": active_preset,
        "caption": _range_caption(date_from, date_to),
    }


def _build_transactions(user_id, *, date_from=None, date_to=None):
    """-> [{'id', 'date': 'DD Mon YYYY', 'description', 'category', 'amount': float}]"""
    rows = get_recent_expenses(user_id, date_from=date_from, date_to=date_to)
    return [
        {
            "id": row["id"],
            "date": _format_date(row["date"]),
            "description": row["description"] or "",
            "category": row["category"],
            "amount": float(row["amount"]),
        }
        for row in rows
    ]


def _build_stats(user_id, categories, *, date_from=None, date_to=None):
    """-> {'total_spent': float, 'transaction_count': int, 'top_category': str | None}

    ``categories`` is _build_categories output: sorted by amount DESC, name ASC.
    """
    summary = get_expense_summary(user_id, date_from=date_from, date_to=date_to)
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


def _build_categories(user_id, *, date_from=None, date_to=None):
    """-> [{'name': str, 'amount': float, 'pct': float (1dp)}], [] when no spend."""
    return _category_pcts(
        get_category_totals(user_id, date_from=date_from, date_to=date_to)
    )


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
        return (
            render_template("register.html", error=error, name=name, email=email),
            status,
        )
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
        return (
            render_template("login.html", error=LOGIN_REQUIRED_ERROR, email=email),
            400,
        )

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return (
            render_template("login.html", error=INVALID_LOGIN_ERROR, email=email),
            401,
        )

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
    row = _session_user()
    if row is None:
        return redirect(url_for("login"))
    user_id = row["id"]

    parsed = _parse_date_filter(request.args)
    date_range = {"date_from": parsed["date_from"], "date_to": parsed["date_to"]}
    categories = _build_categories(user_id, **date_range)
    return render_template(
        "profile.html",
        user=_build_user(row),
        stats=_build_stats(user_id, categories, **date_range),
        transactions=_build_transactions(user_id, **date_range),
        categories=categories,
        date_filter=_build_filter(parsed, date.today()),
    )


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    user = _session_user()
    if user is None:
        return redirect(url_for("login"))

    today = date.today()
    if request.method == "GET":
        return _render_add_expense(_default_expense_values(today), today)

    values, error = _parse_expense_form(request.form, today)
    if error:
        form_values = _expense_form_values(request.form)
        return _render_add_expense(form_values, today, error), 400
    create_expense(user["id"], **values)  # user_id comes from the session only
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Expense edit / delete routes (owner only)                           #
# ------------------------------------------------------------------ #


@app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
def edit_expense(expense_id):
    user = _session_user()
    if user is None:
        return redirect(url_for("login"))
    # Scoped to the session user: someone else's id looks like a missing one.
    expense = get_expense_by_id(expense_id, user["id"])
    if expense is None:
        abort(404)

    today = date.today()
    if request.method == "GET":
        return _render_edit_expense(expense_id, _expense_row_values(expense), today)

    if not _csrf_valid(request.form):
        abort(400)
    values, error = _parse_expense_form(request.form, today)
    if error:
        form_values = _expense_form_values(request.form)
        return _render_edit_expense(expense_id, form_values, today, error), 400
    if not update_expense(expense_id, user["id"], **values):
        abort(404)  # removed between lookup and save
    return redirect(url_for("profile"))


@app.route("/expenses/<int:expense_id>/delete", methods=["GET", "POST"])
def delete_expense(expense_id):
    user = _session_user()
    if user is None:
        return redirect(url_for("login"))
    # Scoped to the session user: someone else's id looks like a missing one.
    expense = get_expense_by_id(expense_id, user["id"])
    if expense is None:
        abort(404)

    if request.method == "GET":  # GET only confirms; it never deletes
        return _render_delete_expense(expense_id, expense)

    if not _csrf_valid(request.form):
        abort(400)
    if not delete_expense_row(expense_id, user["id"]):
        abort(404)  # already deleted (double submit / another tab)
    return redirect(url_for("profile"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
