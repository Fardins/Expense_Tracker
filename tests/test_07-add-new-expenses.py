"""Tests for Step 7 - add new expenses (spec 07-add-new-expenses).

Written from the spec only. Uses the conftest `app` fixture (temp DB, seeded
demo user) and pytest-flask's `client`. Never imports `app` at module level.
"""
import importlib
import math
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from flask import url_for

from database import db

DEMO = {"email": "demo@spendly.com", "password": "demo123"}
USER_B = {"name": "Other User", "email": "other@example.com", "password": "otherpass12"}

ERR_AMOUNT = "Enter an amount greater than 0."
ERR_TOO_LARGE = "Amount is too large."
ERR_CATEGORY = "Choose a valid category."
ERR_DATE = "Enter a valid date."
ERR_FUTURE = "Date cannot be in the future."
ERR_DESC = "Description must be 200 characters or fewer."

FIXED_TODAY = date(2026, 11, 2)
ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _login(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


def _text(response):
    return response.get_data(as_text=True)


def _input_tag(page, name):
    for m in re.finditer(r"<input\b[^>]*>", page):
        tag = m.group(0)
        if re.search(r'name="%s"' % re.escape(name), tag):
            return tag
    return None


def _shift_month(d, delta):
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def _url(app, endpoint, **values):
    with app.test_request_context():
        return url_for(endpoint, **values)


def _add_url(app):
    return _url(app, "add_expense")


def _profile_url(app, **params):
    return _url(app, "profile", **params)


def _count_expenses(user_id=None):
    conn = db.get_db()
    try:
        if user_id is None:
            return conn.execute("SELECT COUNT(*) AS n FROM expenses").fetchone()["n"]
        return conn.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
    finally:
        conn.close()


def _user_id(email):
    conn = db.get_db()
    try:
        return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
    finally:
        conn.close()


def _last_expense():
    conn = db.get_db()
    try:
        return conn.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()


def _error_banner(page):
    m = re.search(r'<div\b[^>]*class="[^"]*expense-error[^"]*"[^>]*>(.*?)</div>', page, re.S)
    if not m:
        return None
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()


def _selected_option(page):
    m = re.search(r'<option\b[^>]*value="([^"]*)"[^>]*\bselected\b[^>]*>', page)
    return m.group(1) if m else None


def _form(**overrides):
    data = {
        "amount": "250",
        "category": "Food",
        "date": date.today().isoformat(),
        "description": "Dinner",
    }
    data.update(overrides)
    return data


def _parse(form, today=FIXED_TODAY):
    return importlib.import_module("app")._parse_expense_form(form, today)


def _valid_form(**overrides):
    data = {"amount": "12.50", "category": "Food", "date": "2026-11-01", "description": "x"}
    data.update(overrides)
    return data


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def demo_client(client):
    _login(client, DEMO["email"], DEMO["password"])
    return client


@pytest.fixture
def demo_id(app):
    return _user_id(DEMO["email"])


@pytest.fixture
def user_b_id(app):
    return db.create_user(USER_B["name"], USER_B["email"], USER_B["password"])


# --------------------------------------------------------------------------
# _parse_expense_form unit tests
# --------------------------------------------------------------------------
class TestParseExpenseForm:
    def test_valid_form_returns_values_and_no_error(self, app):
        values, error = _parse(_valid_form())
        assert error is None, f"Unexpected error {error!r}"
        assert values == {
            "amount": 12.5,
            "category": "Food",
            "date": "2026-11-01",
            "description": "x",
        }

    def test_amount_rounded_to_two_decimals(self, app):
        values, error = _parse(_valid_form(amount="12.346"))
        assert error is None
        assert values["amount"] == 12.35
        assert isinstance(values["amount"], float)

    def test_whitespace_is_stripped(self, app):
        values, error = _parse(
            _valid_form(amount="  7.5  ", date=" 2026-11-01 ", description="  hello  ")
        )
        assert error is None, f"Unexpected error {error!r}"
        assert values["amount"] == 7.5
        assert values["date"] == "2026-11-01"
        assert values["description"] == "hello"

    @pytest.mark.parametrize(
        "amount", ["", "   ", "0", "-5", "abc", "nan", "inf", "-inf", "0.001", "1e400"]
    )
    def test_bad_amounts_rejected(self, app, amount):
        values, error = _parse(_valid_form(amount=amount))
        assert values is None
        assert error == ERR_AMOUNT

    def test_missing_amount_key_rejected(self, app):
        form = _valid_form()
        del form["amount"]
        values, error = _parse(form)
        assert values is None and error == ERR_AMOUNT

    def test_amount_of_exactly_one_million_is_allowed(self, app):
        values, error = _parse(_valid_form(amount="1000000"))
        assert error is None
        assert values["amount"] == 1000000.0

    @pytest.mark.parametrize("amount", ["1000000.01", "1000001", "99999999"])
    def test_amount_over_one_million_is_too_large(self, app, amount):
        values, error = _parse(_valid_form(amount=amount))
        assert values is None
        assert error == ERR_TOO_LARGE

    @pytest.mark.parametrize("category", ["Crypto", "food", "FOOD", " Food", "", "Food;"])
    def test_bad_category_rejected(self, app, category):
        values, error = _parse(_valid_form(category=category))
        assert values is None
        assert error == ERR_CATEGORY

    def test_every_known_category_accepted(self, app):
        for cat in db.CATEGORIES:
            values, error = _parse(_valid_form(category=cat))
            assert error is None, f"{cat} should be valid, got {error!r}"
            assert values["category"] == cat

    @pytest.mark.parametrize("bad", ["", "2026-13-45", "not-a-date", "11/01/2026", "2026-02-30"])
    def test_bad_date_rejected(self, app, bad):
        values, error = _parse(_valid_form(date=bad))
        assert values is None
        assert error == ERR_DATE

    def test_tomorrow_is_future_error(self, app):
        tomorrow = (FIXED_TODAY + timedelta(days=1)).isoformat()
        values, error = _parse(_valid_form(date=tomorrow))
        assert values is None
        assert error == ERR_FUTURE

    def test_today_is_allowed(self, app):
        values, error = _parse(_valid_form(date=FIXED_TODAY.isoformat()))
        assert error is None
        assert values["date"] == "2026-11-02"

    def test_description_200_chars_allowed(self, app):
        values, error = _parse(_valid_form(description="a" * 200))
        assert error is None
        assert values["description"] == "a" * 200

    def test_description_201_chars_rejected(self, app):
        values, error = _parse(_valid_form(description="a" * 201))
        assert values is None
        assert error == ERR_DESC

    def test_description_length_measured_after_stripping(self, app):
        values, error = _parse(_valid_form(description="  " + "a" * 200 + "  "))
        assert error is None
        assert values["description"] == "a" * 200

    @pytest.mark.parametrize("desc", ["", "     ", None])
    def test_blank_description_becomes_none(self, app, desc):
        form = _valid_form()
        if desc is None:
            del form["description"]
        else:
            form["description"] = desc
        values, error = _parse(form)
        assert error is None
        assert values["description"] is None

    def test_first_error_wins_amount_over_everything(self, app):
        values, error = _parse(
            {"amount": "abc", "category": "Crypto", "date": "bad", "description": "a" * 300}
        )
        assert values is None and error == ERR_AMOUNT

    def test_first_error_wins_category_over_date_and_description(self, app):
        values, error = _parse(
            {"amount": "5", "category": "Crypto", "date": "bad", "description": "a" * 300}
        )
        assert values is None and error == ERR_CATEGORY

    def test_first_error_wins_date_over_description(self, app):
        values, error = _parse(
            {"amount": "5", "category": "Food", "date": "bad", "description": "a" * 300}
        )
        assert values is None and error == ERR_DATE

    def test_plain_dict_input_works(self, app):
        values, error = _parse(dict(_valid_form()))
        assert error is None and values is not None

    def test_nan_and_inf_not_leaked_into_values(self, app):
        for amount in ("nan", "inf"):
            values, _ = _parse(_valid_form(amount=amount))
            assert values is None, f"{amount} must not produce values"
        values, _ = _parse(_valid_form())
        assert math.isfinite(values["amount"])


# --------------------------------------------------------------------------
# db.create_expense
# --------------------------------------------------------------------------
class TestCreateExpense:
    def test_returns_new_id_and_stores_row(self, app, demo_id):
        new_id = db.create_expense(demo_id, 42.5, "Health", "2026-01-05", "Checkup")
        assert isinstance(new_id, int) and new_id > 0
        conn = db.get_db()
        try:
            row = conn.execute("SELECT * FROM expenses WHERE id = ?", (new_id,)).fetchone()
        finally:
            conn.close()
        assert row["user_id"] == demo_id
        assert row["amount"] == 42.5
        assert row["category"] == "Health"
        assert row["date"] == "2026-01-05"
        assert row["description"] == "Checkup"

    def test_missing_description_stored_as_null(self, app, demo_id):
        new_id = db.create_expense(demo_id, 10, "Food", "2026-01-05")
        conn = db.get_db()
        try:
            row = conn.execute("SELECT description FROM expenses WHERE id = ?", (new_id,)).fetchone()
        finally:
            conn.close()
        assert row["description"] is None

    def test_ids_are_distinct_for_successive_inserts(self, app, demo_id):
        a = db.create_expense(demo_id, 1, "Food", "2026-01-05")
        b = db.create_expense(demo_id, 2, "Food", "2026-01-05")
        assert a != b

    def test_sql_injection_in_description_stored_literally(self, app, demo_id):
        payload = "'); DROP TABLE expenses;--"
        before = _count_expenses()
        new_id = db.create_expense(demo_id, 3, "Food", "2026-01-05", payload)
        assert _count_expenses() == before + 1, "Table must be intact"
        conn = db.get_db()
        try:
            row = conn.execute("SELECT description FROM expenses WHERE id = ?", (new_id,)).fetchone()
        finally:
            conn.close()
        assert row["description"] == payload


# --------------------------------------------------------------------------
# Access rules
# --------------------------------------------------------------------------
class TestAccess:
    def test_logged_out_get_redirects_to_login(self, client, app):
        response = client.get(_add_url(app))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_logged_out_post_redirects_to_login_and_inserts_nothing(self, client, app):
        before = _count_expenses()
        response = client.post(_add_url(app), data=_form())
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _count_expenses() == before, "Nothing may be inserted when logged out"

    def test_stale_session_get_clears_session_and_redirects(self, client, app):
        with client.session_transaction() as sess:
            sess["user_id"] = 9999
        response = client.get(_add_url(app))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        with client.session_transaction() as sess:
            assert "user_id" not in sess, "Stale session must be cleared"

    def test_stale_session_post_redirects_and_inserts_nothing(self, client, app):
        before = _count_expenses()
        with client.session_transaction() as sess:
            sess["user_id"] = 9999
        response = client.post(_add_url(app), data=_form())
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _count_expenses() == before


# --------------------------------------------------------------------------
# GET form
# --------------------------------------------------------------------------
class TestGetForm:
    def test_returns_200_with_heading(self, demo_client, app):
        response = demo_client.get(_add_url(app))
        assert response.status_code == 200
        assert "Add an expense" in _text(response)

    def test_shows_all_categories_with_first_selected(self, demo_client, app):
        page = _text(demo_client.get(_add_url(app)))
        assert len(db.CATEGORIES) == 7
        for cat in db.CATEGORIES:
            assert f'value="{cat}"' in page, f"Option for {cat} missing"
        assert len(re.findall(r"<option\b", page)) == 7
        assert _selected_option(page) == db.CATEGORIES[0]
        assert db.CATEGORIES[0] == "Food"

    def test_date_defaults_to_today_with_max_today(self, demo_client, app):
        page = _text(demo_client.get(_add_url(app)))
        tag = _input_tag(page, "date")
        assert tag is not None, "date input missing"
        today = date.today().isoformat()
        assert 'type="date"' in tag
        assert f'value="{today}"' in tag, "Date should default to today"
        assert f'max="{today}"' in tag, "Date max should be today"

    def test_amount_and_description_inputs_attributes(self, demo_client, app):
        page = _text(demo_client.get(_add_url(app)))
        amount = _input_tag(page, "amount")
        assert amount is not None
        assert 'type="number"' in amount and 'step="0.01"' in amount
        assert 'min="0.01"' in amount and 'max="1000000"' in amount
        assert "required" in amount
        desc = _input_tag(page, "description")
        assert desc is not None
        assert 'maxlength="200"' in desc
        assert "required" not in desc, "Description is optional"

    def test_form_posts_to_add_url(self, demo_client, app):
        page = _text(demo_client.get(_add_url(app)))
        form = re.search(r"<form\b[^>]*>", page)
        assert form, "Form missing"
        tag = form.group(0).lower()
        assert 'method="post"' in tag
        assert f'action="{_add_url(app)}"' in tag

    def test_every_field_has_a_matching_label(self, demo_client, app):
        page = _text(demo_client.get(_add_url(app)))
        for name in ("amount", "category", "date", "description"):
            m = re.search(r'<(?:input|select)\b[^>]*name="%s"[^>]*>' % name, page)
            assert m, f"Field {name} missing"
            id_m = re.search(r'\bid="([^"]+)"', m.group(0))
            assert id_m, f"Field {name} needs an id"
            assert re.search(r'<label\b[^>]*for="%s"' % re.escape(id_m.group(1)), page), (
                f"No label for {name}"
            )

    def test_shows_rupee_prefix_submit_and_cancel(self, demo_client, app):
        page = _text(demo_client.get(_add_url(app)))
        assert "₹" in page
        assert "Add expense" in page
        assert "Cancel" in page
        assert f'href="{_profile_url(app)}"' in page, "Cancel must link to the profile"

    def test_no_error_banner_on_get(self, demo_client, app):
        page = _text(demo_client.get(_add_url(app)))
        assert _error_banner(page) is None

    def test_profile_add_expense_button_points_to_form(self, demo_client, app):
        page = _text(demo_client.get(_profile_url(app)))
        assert f'href="{_add_url(app)}"' in page


# --------------------------------------------------------------------------
# Valid POST
# --------------------------------------------------------------------------
class TestValidPost:
    def test_definition_of_done_flow(self, demo_client, app, demo_id):
        response = demo_client.post(_add_url(app), data=_form())
        assert response.status_code == 302, "Success must redirect (PRG)"
        assert response.headers["Location"].endswith(_profile_url(app))

        page = _text(demo_client.get(_profile_url(app)))
        total = re.search(r"profile-total-spent[^>]*>\s*([^<]+)<", page)
        assert total and "₹472.19" in total.group(1), "Total should be 222.19 + 250"
        count = re.search(r"Transactions</p>\s*<p[^>]*>\s*(\d+)\s*<", page)
        assert count and count.group(1) == "9", "Should show 9 transactions"
        first_row = re.search(r"<tbody>\s*<tr>(.*?)</tr>", page, re.S)
        assert first_row and "Dinner" in first_row.group(1), "Dinner should be first"

    def test_row_stored_with_session_user_and_values(self, demo_client, app, demo_id):
        demo_client.post(_add_url(app), data=_form(amount="12.346", description="Rounded"))
        row = _last_expense()
        assert row["user_id"] == demo_id
        assert row["amount"] == 12.35
        assert row["category"] == "Food"
        assert row["date"] == date.today().isoformat()
        assert row["description"] == "Rounded"

    def test_row_count_increments_by_one(self, demo_client, app, demo_id):
        before = _count_expenses(demo_id)
        demo_client.post(_add_url(app), data=_form())
        assert _count_expenses(demo_id) == before + 1

    @pytest.mark.parametrize("desc", ["", "    "])
    def test_blank_description_stored_as_null_and_still_listed(self, demo_client, app, desc):
        demo_client.post(_add_url(app), data=_form(amount="77.77", description=desc))
        assert _last_expense()["description"] is None
        page = _text(demo_client.get(_profile_url(app)))
        assert "₹77.77" in page, "Expense without description should still render"
        assert "₹299.96" in page, "Total should include the new expense"

    def test_forged_user_id_is_ignored(self, demo_client, app, demo_id, user_b_id):
        before_b = _count_expenses(user_b_id)
        demo_client.post(_add_url(app), data=_form(user_id=str(user_b_id)))
        row = _last_expense()
        assert row["user_id"] == demo_id, "Expense must belong to the session user"
        assert _count_expenses(user_b_id) == before_b

    def test_users_expense_not_visible_to_other_user(self, client, app, demo_id, user_b_id):
        _login(client, DEMO["email"], DEMO["password"])
        client.post(_add_url(app), data=_form(description="A-private-note"))
        client.get("/logout")
        _login(client, USER_B["email"], USER_B["password"])
        page = _text(client.get(_profile_url(app)))
        assert "A-private-note" not in page, "User A's expense leaked to user B"
        assert "₹0.00" in page

    def test_last_month_expense_shows_under_last_month_not_this_month(self, demo_client, app):
        today = date.today()
        last_month_day = _shift_month(today, -1).replace(day=15)
        response = demo_client.post(
            _add_url(app),
            data=_form(date=last_month_day.isoformat(), description="LastMonthItem"),
        )
        assert response.status_code == 302
        first_prev = _shift_month(today, -1)
        last_prev = today.replace(day=1) - timedelta(days=1)
        last_page = _text(
            demo_client.get(
                _profile_url(app, **{"from": first_prev.isoformat(), "to": last_prev.isoformat()})
            )
        )
        assert "LastMonthItem" in last_page, "Should appear under Last month"
        this_page = _text(
            demo_client.get(
                _profile_url(app, **{"from": today.replace(day=1).isoformat(), "to": today.isoformat()})
            )
        )
        assert "LastMonthItem" not in this_page, "Should not appear under This month"

    def test_success_response_is_not_a_rendered_page(self, demo_client, app):
        response = demo_client.post(_add_url(app), data=_form())
        assert response.status_code == 302
        assert "Add an expense" not in _text(response)

    def test_expense_dated_today_accepted_and_boundary_amounts(self, demo_client, app):
        for amount in ("0.01", "1000000"):
            response = demo_client.post(_add_url(app), data=_form(amount=amount))
            assert response.status_code == 302, f"{amount} should be accepted"


# --------------------------------------------------------------------------
# Invalid POST
# --------------------------------------------------------------------------
def _tomorrow():
    return (date.today() + timedelta(days=1)).isoformat()


INVALID_CASES = [
    ({"amount": ""}, ERR_AMOUNT),
    ({"amount": "0"}, ERR_AMOUNT),
    ({"amount": "-5"}, ERR_AMOUNT),
    ({"amount": "abc"}, ERR_AMOUNT),
    ({"amount": "nan"}, ERR_AMOUNT),
    ({"amount": "inf"}, ERR_AMOUNT),
    ({"amount": "0.001"}, ERR_AMOUNT),
    ({"amount": "1000001"}, ERR_TOO_LARGE),
    ({"category": "Crypto"}, ERR_CATEGORY),
    ({"category": "food"}, ERR_CATEGORY),
    ({"category": ""}, ERR_CATEGORY),
    ({"date": "2026-13-45"}, ERR_DATE),
    ({"date": ""}, ERR_DATE),
    ({"date": "garbage"}, ERR_DATE),
    ({"date": "FUTURE"}, ERR_FUTURE),
    ({"description": "a" * 201}, ERR_DESC),
]


class TestInvalidPost:
    @pytest.mark.parametrize("override,message", INVALID_CASES)
    def test_invalid_input_returns_400_with_message_and_inserts_nothing(
        self, demo_client, app, override, message
    ):
        override = {k: (_tomorrow() if v == "FUTURE" else v) for k, v in override.items()}
        before = _count_expenses()
        response = demo_client.post(_add_url(app), data=_form(**override))
        assert response.status_code == 400, f"Expected 400 for {override}"
        assert _error_banner(_text(response)) == message
        assert 'role="alert"' in _text(response)
        assert _count_expenses() == before, "Nothing may be inserted on error"

    def test_missing_fields_entirely_returns_400_not_500(self, demo_client, app):
        before = _count_expenses()
        response = demo_client.post(_add_url(app), data={})
        assert response.status_code == 400
        assert _error_banner(_text(response)) == ERR_AMOUNT
        assert _count_expenses() == before

    def test_only_first_error_reported(self, demo_client, app):
        response = demo_client.post(
            _add_url(app),
            data=_form(amount="abc", category="Crypto", date="bad", description="a" * 300),
        )
        assert response.status_code == 400
        page = _text(response)
        assert _error_banner(page) == ERR_AMOUNT
        for other in (ERR_CATEGORY, ERR_DATE, ERR_DESC):
            assert other not in page, f"Only the first error should show, saw {other!r}"

    def test_sticky_values_after_failed_post(self, demo_client, app):
        data = _form(
            amount="abc", category="Bills", date="2020-05-06", description="Keep me"
        )
        response = demo_client.post(_add_url(app), data=data)
        page = _text(response)
        assert response.status_code == 400
        assert _selected_option(page) == "Bills", "Category must stay selected"
        assert 'value="2020-05-06"' in _input_tag(page, "date")
        assert 'value="abc"' in _input_tag(page, "amount") or "abc" in _input_tag(page, "amount")
        assert 'value="Keep me"' in _input_tag(page, "description")

    def test_sticky_amount_after_other_error(self, demo_client, app):
        response = demo_client.post(
            _add_url(app), data=_form(amount="33.5", date="2020-13-45", category="Health")
        )
        page = _text(response)
        assert _error_banner(page) == ERR_DATE
        assert 'value="33.5"' in _input_tag(page, "amount")
        assert _selected_option(page) == "Health"

    def test_script_in_description_is_escaped(self, demo_client, app):
        payload = '"><script>alert(1)</script>'
        response = demo_client.post(_add_url(app), data=_form(amount="bad", description=payload))
        page = _text(response)
        assert response.status_code == 400
        assert "<script>alert(1)</script>" not in page, "Description must be escaped"

    def test_forged_user_id_on_invalid_post_inserts_nothing(self, demo_client, app, user_b_id):
        before = _count_expenses()
        response = demo_client.post(_add_url(app), data=_form(amount="0", user_id=str(user_b_id)))
        assert response.status_code == 400
        assert _count_expenses() == before


# --------------------------------------------------------------------------
# Static checks on source files (no SQL in app.py, template/CSS hygiene)
# --------------------------------------------------------------------------
class TestStaticHygiene:
    def test_app_py_contains_no_sql(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        assert not re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\b\s", source), "SQL found in app.py"
        assert ".execute(" not in source, "app.py must not run queries"

    def test_template_has_no_safe_filter_or_inline_style(self):
        source = (ROOT / "templates" / "add_expense.html").read_text(encoding="utf-8")
        assert "|safe" not in source.replace(" ", ""), "|safe is forbidden"
        assert "<style" not in source, "No inline <style> tags"
        assert "style=" not in source, "No inline style attributes"
        assert 'action="/' not in source and 'href="/' not in source, "No hardcoded paths"

    def test_css_has_no_hex_colours_and_has_mobile_media_query(self):
        source = (ROOT / "static" / "css" / "expense.css").read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source), "Hex colours are forbidden"
        assert re.search(r"@media[^{]*600px", source), "Expected a 600px media query"
