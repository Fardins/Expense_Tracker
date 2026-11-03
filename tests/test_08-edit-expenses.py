"""Tests for Step 8 - edit expenses (spec 08-edit-expenses).

Written from the spec and plan only. Uses the conftest `app` fixture (temp DB,
seeded demo user) and pytest-flask's `client`. Never imports `app` at module
level. Helpers are copied from test_07 rather than imported.
"""

import inspect
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


def _attr(tag, attr):
    m = re.search(r'\b%s="([^"]*)"' % re.escape(attr), tag)
    return m.group(1) if m else None


def _shift_month(d, delta):
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def _url(app, endpoint, **values):
    with app.test_request_context():
        return url_for(endpoint, **values)


def _edit_url(app, expense_id):
    return _url(app, "edit_expense", expense_id=expense_id)


def _profile_url(app, **params):
    return _url(app, "profile", **params)


def _error_banner(page):
    m = re.search(
        r'<div\b[^>]*class="[^"]*expense-error[^"]*"[^>]*>(.*?)</div>', page, re.S
    )
    if not m:
        return None
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()


def _selected_option(page):
    m = re.search(r'<option\b[^>]*value="([^"]*)"[^>]*\bselected\b[^>]*>', page)
    return m.group(1) if m else None


def _user_id(email):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()["id"]
    finally:
        conn.close()


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


def _expense_row(expense_id):
    """Full raw row (including user_id and created_at) as a plain dict."""
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _expense_id_by_description(description):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT id FROM expenses WHERE description = ?", (description,)
        ).fetchone()["id"]
    finally:
        conn.close()


def _category_total_db(user_id, category):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS t FROM expenses WHERE user_id = ? AND category = ?",
            (user_id, category),
        ).fetchone()["t"]
    finally:
        conn.close()


def _category_amount_on_page(page, category):
    """Return the amount shown for `category` in the breakdown list, or None."""
    m = re.search(
        r'<li\b[^>]*class="[^"]*profile-cat--%s\b[^"]*"[^>]*>.*?profile-cat-amount">\s*₹([\d.]+)'
        % re.escape(category.lower()),
        page,
        re.S,
    )
    return float(m.group(1)) if m else None


def _csrf_from_page(page):
    tag = _input_tag(page, "csrf_token")
    assert tag is not None, "Hidden csrf_token input missing"
    value = _attr(tag, "value")
    assert value, "csrf_token input has no value"
    return value


def _get_token(client, app, expense_id):
    response = client.get(_edit_url(app, expense_id))
    assert response.status_code == 200, "Edit form must load to read the token"
    return _csrf_from_page(_text(response))


def _form(token, **overrides):
    data = {
        "csrf_token": token,
        "amount": "20",
        "category": "Food",
        "date": date.today().isoformat(),
        "description": "Lunch",
    }
    data.update(overrides)
    return data


def _total_and_count(page):
    total = re.search(r"profile-total-spent[^>]*>\s*([^<]+)<", page)
    count = re.search(r"Transactions</p>\s*<p[^>]*>\s*(\d+)\s*<", page)
    return (
        total.group(1).strip() if total else None,
        count.group(1) if count else None,
    )


def _tomorrow():
    return (date.today() + timedelta(days=1)).isoformat()


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


@pytest.fixture
def lunch_id(app):
    return _expense_id_by_description("Lunch")


@pytest.fixture
def token(demo_client, app, lunch_id):
    return _get_token(demo_client, app, lunch_id)


# --------------------------------------------------------------------------
# db helpers
# --------------------------------------------------------------------------
class TestDbHelpers:
    def test_get_expense_by_id_returns_owner_row(self, app, demo_id, lunch_id):
        row = db.get_expense_by_id(lunch_id, demo_id)
        assert row is not None
        assert row["id"] == lunch_id
        assert row["amount"] == 12.5
        assert row["category"] == "Food"
        assert row["description"] == "Lunch"
        assert row["date"], "date should be present"

    def test_get_expense_by_id_wrong_user_returns_none(self, app, user_b_id, lunch_id):
        assert db.get_expense_by_id(lunch_id, user_b_id) is None

    def test_get_expense_by_id_missing_returns_none(self, app, demo_id):
        assert db.get_expense_by_id(999999, demo_id) is None

    def test_update_expense_changes_values_and_returns_true(
        self, app, demo_id, lunch_id
    ):
        result = db.update_expense(
            lunch_id, demo_id, 33.3, "Health", "2026-01-05", "Changed"
        )
        assert result is True
        row = _expense_row(lunch_id)
        assert row["amount"] == 33.3
        assert row["category"] == "Health"
        assert row["date"] == "2026-01-05"
        assert row["description"] == "Changed"

    def test_update_expense_preserves_user_id_and_created_at(
        self, app, demo_id, lunch_id
    ):
        before = _expense_row(lunch_id)
        db.update_expense(lunch_id, demo_id, 1.0, "Other", "2026-01-05", "x")
        after = _expense_row(lunch_id)
        assert after["id"] == before["id"]
        assert after["user_id"] == before["user_id"]
        assert after["created_at"] == before["created_at"]

    def test_update_expense_default_description_stored_as_null(
        self, app, demo_id, lunch_id
    ):
        assert db.update_expense(lunch_id, demo_id, 5, "Food", "2026-01-05") is True
        assert _expense_row(lunch_id)["description"] is None

    def test_update_expense_wrong_user_returns_false_and_changes_nothing(
        self, app, user_b_id, lunch_id
    ):
        before = _expense_row(lunch_id)
        result = db.update_expense(
            lunch_id, user_b_id, 99, "Health", "2026-01-05", "Hacked"
        )
        assert result is False
        assert _expense_row(lunch_id) == before

    def test_update_expense_missing_id_returns_false(self, app, demo_id):
        before = _count_expenses()
        assert db.update_expense(999999, demo_id, 5, "Food", "2026-01-05") is False
        assert _count_expenses() == before, "update must never insert"

    def test_update_expense_does_not_touch_other_rows(self, app, demo_id, lunch_id):
        other_id = _expense_id_by_description("Bus fare")
        before = _expense_row(other_id)
        db.update_expense(lunch_id, demo_id, 1, "Food", "2026-01-05", "x")
        assert _expense_row(other_id) == before

    def test_update_expense_sql_injection_stored_literally(
        self, app, demo_id, lunch_id
    ):
        payload = "'); DROP TABLE expenses;--"
        count = _count_expenses()
        assert (
            db.update_expense(lunch_id, demo_id, 1, "Food", "2026-01-05", payload)
            is True
        )
        assert _count_expenses() == count, "Table must be intact"
        assert _expense_row(lunch_id)["description"] == payload

    def test_get_recent_expenses_rows_include_id_as_last_column(self, app, demo_id):
        rows = db.get_recent_expenses(demo_id)
        assert len(rows) == 8
        assert list(rows[0].keys()) == [
            "date",
            "description",
            "category",
            "amount",
            "id",
        ]
        ids = {row["id"] for row in rows}
        assert len(ids) == 8, "Each row needs a distinct id"
        for row in rows:
            assert db.get_expense_by_id(row["id"], demo_id) is not None


# --------------------------------------------------------------------------
# Access rules
# --------------------------------------------------------------------------
class TestAccess:
    def test_logged_out_get_redirects_to_login(self, client, app, lunch_id):
        response = client.get(_edit_url(app, lunch_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_logged_out_post_redirects_and_row_unchanged(self, client, app, lunch_id):
        before = _expense_row(lunch_id)
        response = client.post(
            _edit_url(app, lunch_id), data=_form("whatever", amount="99")
        )
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _expense_row(lunch_id) == before

    def test_logged_out_non_existent_id_redirects_not_404(self, client, app):
        response = client.get(_edit_url(app, 999999))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_stale_session_get_clears_session_and_redirects(
        self, client, app, lunch_id
    ):
        with client.session_transaction() as sess:
            sess["user_id"] = 9999
        response = client.get(_edit_url(app, lunch_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        with client.session_transaction() as sess:
            assert "user_id" not in sess, "Stale session must be cleared"

    def test_stale_session_post_redirects_and_row_unchanged(
        self, client, app, lunch_id
    ):
        before = _expense_row(lunch_id)
        with client.session_transaction() as sess:
            sess["user_id"] = 9999
            sess["csrf_token"] = "tok"
        response = client.post(_edit_url(app, lunch_id), data=_form("tok", amount="99"))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _expense_row(lunch_id) == before

    @pytest.mark.parametrize("bad_id", ["999999", "abc", "0", "-1"])
    def test_unknown_or_non_integer_id_get_returns_404(self, demo_client, bad_id):
        response = demo_client.get(f"/expenses/{bad_id}/edit")
        assert response.status_code == 404

    def test_missing_id_post_returns_404(self, demo_client, app, token):
        before = _count_expenses()
        response = demo_client.post(_edit_url(app, 999999), data=_form(token))
        assert response.status_code == 404
        assert _count_expenses() == before

    def test_missing_id_post_without_token_is_404_not_400(self, demo_client, app):
        response = demo_client.post(_edit_url(app, 999999), data=_form(""))
        assert response.status_code == 404, "Ownership check runs before CSRF"

    def test_other_users_expense_get_returns_404(
        self, client, app, lunch_id, user_b_id
    ):
        _login(client, USER_B["email"], USER_B["password"])
        response = client.get(_edit_url(app, lunch_id))
        assert response.status_code == 404, "Must be 404, never 403"
        assert "Lunch" not in _text(response), "No data from another user may leak"

    def test_other_users_expense_post_returns_404_and_row_unchanged(
        self, client, app, lunch_id, user_b_id
    ):
        before = _expense_row(lunch_id)
        _login(client, USER_B["email"], USER_B["password"])
        with client.session_transaction() as sess:
            sess["csrf_token"] = "tok"
        response = client.post(_edit_url(app, lunch_id), data=_form("tok", amount="99"))
        assert response.status_code == 404
        assert _expense_row(lunch_id) == before

    def test_other_users_expense_post_without_token_is_404_not_400(
        self, client, app, lunch_id, user_b_id
    ):
        _login(client, USER_B["email"], USER_B["password"])
        response = client.post(_edit_url(app, lunch_id), data=_form(""))
        assert response.status_code == 404

    def test_logged_in_get_on_own_expense_is_200(self, demo_client, app, lunch_id):
        assert demo_client.get(_edit_url(app, lunch_id)).status_code == 200


# --------------------------------------------------------------------------
# CSRF
# --------------------------------------------------------------------------
class TestCsrf:
    def test_form_has_hidden_token_matching_session(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_edit_url(app, lunch_id)))
        tag = _input_tag(page, "csrf_token")
        assert tag is not None
        assert 'type="hidden"' in tag
        with demo_client.session_transaction() as sess:
            assert sess.get("csrf_token"), "Session must hold the token"
            assert _attr(tag, "value") == sess["csrf_token"]

    def test_token_is_stable_across_requests(self, demo_client, app, lunch_id):
        first = _get_token(demo_client, app, lunch_id)
        second = _get_token(demo_client, app, lunch_id)
        assert first == second

    def test_tokens_differ_between_sessions(self, app, lunch_id):
        c1 = app.test_client()
        c2 = app.test_client()
        _login(c1, DEMO["email"], DEMO["password"])
        _login(c2, DEMO["email"], DEMO["password"])
        assert _get_token(c1, app, lunch_id) != _get_token(c2, app, lunch_id)

    def test_valid_token_allows_update(self, demo_client, app, lunch_id, token):
        response = demo_client.post(_edit_url(app, lunch_id), data=_form(token))
        assert response.status_code == 302
        assert _expense_row(lunch_id)["amount"] == 20.0

    def test_missing_token_field_returns_400_and_row_unchanged(
        self, demo_client, app, lunch_id, token
    ):
        before = _expense_row(lunch_id)
        data = _form(token, amount="99")
        del data["csrf_token"]
        response = demo_client.post(_edit_url(app, lunch_id), data=data)
        assert response.status_code == 400
        assert _expense_row(lunch_id) == before

    @pytest.mark.parametrize("bad", ["", "wrong-token", "é€漢字", " ", "A" * 500])
    def test_wrong_token_returns_400_and_row_unchanged(
        self, demo_client, app, lunch_id, token, bad
    ):
        before = _expense_row(lunch_id)
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form(bad, amount="99")
        )
        assert response.status_code == 400, "Bad token must be 400, never 500"
        assert _expense_row(lunch_id) == before

    def test_token_from_other_session_is_rejected(self, app, lunch_id):
        other = app.test_client()
        _login(other, DEMO["email"], DEMO["password"])
        stolen = _get_token(other, app, lunch_id)
        victim = app.test_client()
        _login(victim, DEMO["email"], DEMO["password"])
        _get_token(victim, app, lunch_id)
        before = _expense_row(lunch_id)
        response = victim.post(
            _edit_url(app, lunch_id), data=_form(stolen, amount="99")
        )
        assert response.status_code == 400
        assert _expense_row(lunch_id) == before

    @pytest.mark.parametrize("submitted", ["", "anything", "é"])
    def test_no_session_token_returns_400(self, demo_client, app, lunch_id, submitted):
        with demo_client.session_transaction() as sess:
            sess.pop("csrf_token", None)
        before = _expense_row(lunch_id)
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form(submitted, amount="99")
        )
        assert response.status_code == 400, "An empty session token must never match"
        assert _expense_row(lunch_id) == before

    def test_csrf_checked_before_validation(self, demo_client, app, lunch_id, token):
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form("bad", amount="abc")
        )
        assert response.status_code == 400
        assert (
            _error_banner(_text(response)) is None
        ), "Bad token is a plain 400, not a form error"

    def test_token_set_via_session_transaction_works(self, demo_client, app, lunch_id):
        with demo_client.session_transaction() as sess:
            sess["csrf_token"] = "fixed-token-for-test"
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form("fixed-token-for-test", amount="21")
        )
        assert response.status_code == 302
        assert _expense_row(lunch_id)["amount"] == 21.0

    def test_invalid_post_rerender_includes_matching_token(
        self, demo_client, app, lunch_id, token
    ):
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form(token, amount="0")
        )
        assert response.status_code == 400
        assert _csrf_from_page(_text(response)) == token

    def test_token_still_valid_after_failed_validation(
        self, demo_client, app, lunch_id, token
    ):
        demo_client.post(_edit_url(app, lunch_id), data=_form(token, amount="0"))
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form(token, amount="22")
        )
        assert response.status_code == 302
        assert _expense_row(lunch_id)["amount"] == 22.0

    def test_login_rotates_token(self, client, app, lunch_id):
        _login(client, DEMO["email"], DEMO["password"])
        first = _get_token(client, app, lunch_id)
        client.get("/logout")
        _login(client, DEMO["email"], DEMO["password"])
        assert _get_token(client, app, lunch_id) != first

    def test_add_form_still_has_no_csrf_token(self, demo_client, app):
        page = _text(demo_client.get(_url(app, "add_expense")))
        assert _input_tag(page, "csrf_token") is None
        assert "csrf" not in page.lower()


# --------------------------------------------------------------------------
# GET form
# --------------------------------------------------------------------------
class TestGetForm:
    def test_returns_200_with_title_and_heading(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_edit_url(app, lunch_id)))
        assert re.search(
            r"<title>[^<]*Edit expense", page
        ), "Title should contain 'Edit expense'"
        assert "Edit expense" in page

    def test_lunch_prefill(self, demo_client, app, lunch_id, demo_id):
        page = _text(demo_client.get(_edit_url(app, lunch_id)))
        row = db.get_expense_by_id(lunch_id, demo_id)
        assert 'value="12.50"' in _input_tag(page, "amount"), "Amount must be 2 dp"
        assert _selected_option(page) == "Food"
        assert f'value="{row["date"]}"' in _input_tag(page, "date")
        assert 'value="Lunch"' in _input_tag(page, "description")

    def test_amount_formatted_to_two_decimals_for_whole_number(
        self, demo_client, app, demo_id
    ):
        pharmacy = _expense_id_by_description("Pharmacy")
        page = _text(demo_client.get(_edit_url(app, pharmacy)))
        assert 'value="20.00"' in _input_tag(page, "amount")
        assert _selected_option(page) == "Health"

    def test_null_description_renders_empty_value(
        self, demo_client, app, demo_id, lunch_id
    ):
        db.update_expense(
            lunch_id, demo_id, 12.5, "Food", date.today().isoformat(), None
        )
        page = _text(demo_client.get(_edit_url(app, lunch_id)))
        tag = _input_tag(page, "description")
        assert tag is not None
        assert 'value=""' in tag
        assert "None" not in tag, "NULL must not render as the string None"

    def test_form_posts_to_edit_url(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_edit_url(app, lunch_id)))
        form = re.search(r"<form\b[^>]*>", page)
        assert form, "Form missing"
        tag = form.group(0).lower()
        assert 'method="post"' in tag
        assert f'action="{_edit_url(app, lunch_id)}"' in tag

    def test_shows_all_categories(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_edit_url(app, lunch_id)))
        assert len(re.findall(r"<option\b", page)) == len(db.CATEGORIES)
        for cat in db.CATEGORIES:
            assert f'value="{cat}"' in page

    def test_submit_button_and_cancel_link(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_edit_url(app, lunch_id)))
        assert "Save changes" in page
        assert "Cancel" in page
        assert f'href="{_profile_url(app)}"' in page, "Cancel must link to the profile"

    def test_field_attributes_match_add_form(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_edit_url(app, lunch_id)))
        amount = _input_tag(page, "amount")
        assert 'type="number"' in amount and 'step="0.01"' in amount
        assert 'min="0.01"' in amount and 'max="1000000"' in amount
        assert "required" in amount
        date_tag = _input_tag(page, "date")
        assert 'type="date"' in date_tag
        assert f'max="{date.today().isoformat()}"' in date_tag
        desc = _input_tag(page, "description")
        assert 'maxlength="200"' in desc and "required" not in desc

    def test_every_field_has_a_matching_label(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_edit_url(app, lunch_id)))
        for name in ("amount", "category", "date", "description"):
            m = re.search(r'<(?:input|select)\b[^>]*name="%s"[^>]*>' % name, page)
            assert m, f"Field {name} missing"
            id_m = re.search(r'\bid="([^"]+)"', m.group(0))
            assert id_m, f"Field {name} needs an id"
            assert re.search(r'<label\b[^>]*for="%s"' % re.escape(id_m.group(1)), page)

    def test_no_error_banner_on_get(self, demo_client, app, lunch_id):
        assert _error_banner(_text(demo_client.get(_edit_url(app, lunch_id)))) is None

    def test_description_is_escaped_in_prefill(
        self, demo_client, app, demo_id, lunch_id
    ):
        payload = '"><script>alert(1)</script>'
        db.update_expense(
            lunch_id, demo_id, 12.5, "Food", date.today().isoformat(), payload
        )
        page = _text(demo_client.get(_edit_url(app, lunch_id)))
        assert "<script>alert(1)</script>" not in page


# --------------------------------------------------------------------------
# Valid POST
# --------------------------------------------------------------------------
class TestValidPost:
    def test_definition_of_done_flow(self, demo_client, app, lunch_id, token):
        before_total, before_count = _total_and_count(
            _text(demo_client.get(_profile_url(app)))
        )
        assert before_total == "₹222.19" and before_count == "8"

        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form(token, amount="20")
        )
        assert response.status_code == 302, "Success must redirect (PRG)"
        assert response.headers["Location"].endswith(_profile_url(app))

        page = _text(demo_client.get(_profile_url(app)))
        total, count = _total_and_count(page)
        assert total == "₹229.69", "Total should rise by 7.50"
        assert count == "8", "Transaction count must be unchanged"
        lunch_row = re.search(
            r"<tr>(?:(?!</tr>).)*Lunch(?:(?!</tr>).)*</tr>", page, re.S
        )
        assert lunch_row and "₹20.00" in lunch_row.group(
            0
        ), "Lunch row should show ₹20.00"

    def test_success_response_is_not_a_rendered_page(
        self, demo_client, app, lunch_id, token
    ):
        response = demo_client.post(_edit_url(app, lunch_id), data=_form(token))
        assert response.status_code == 302
        assert "Save changes" not in _text(response)

    def test_row_updated_with_submitted_values(self, demo_client, app, lunch_id, token):
        demo_client.post(
            _edit_url(app, lunch_id),
            data=_form(
                token,
                amount="12.346",
                category="Health",
                date="2026-01-05",
                description="  Renamed  ",
            ),
        )
        row = _expense_row(lunch_id)
        assert row["amount"] == 12.35
        assert row["category"] == "Health"
        assert row["date"] == "2026-01-05"
        assert row["description"] == "Renamed"

    def test_id_user_and_created_at_preserved_and_no_new_row(
        self, demo_client, app, lunch_id, demo_id, token
    ):
        before = _expense_row(lunch_id)
        count = _count_expenses()
        demo_client.post(_edit_url(app, lunch_id), data=_form(token, amount="31"))
        after = _expense_row(lunch_id)
        assert after["id"] == before["id"]
        assert after["user_id"] == before["user_id"] == demo_id
        assert after["created_at"] == before["created_at"]
        assert _count_expenses() == count, "Editing must not insert a row"

    def test_only_target_row_changes(self, demo_client, app, lunch_id, token):
        other_id = _expense_id_by_description("Bus fare")
        before = _expense_row(other_id)
        demo_client.post(_edit_url(app, lunch_id), data=_form(token, amount="31"))
        assert _expense_row(other_id) == before

    def test_category_change_updates_breakdown(
        self, demo_client, app, lunch_id, demo_id, token
    ):
        page_before = _text(demo_client.get(_profile_url(app)))
        food_before = _category_amount_on_page(page_before, "Food")
        health_before = _category_amount_on_page(page_before, "Health")
        assert health_before is not None
        demo_client.post(
            _edit_url(app, lunch_id),
            data=_form(token, amount="12.50", category="Health"),
        )
        page = _text(demo_client.get(_profile_url(app)))
        health_after = _category_amount_on_page(page, "Health")
        assert health_after == pytest.approx(health_before + 12.5)
        assert health_after == pytest.approx(_category_total_db(demo_id, "Health"))
        food_after = _category_amount_on_page(page, "Food")
        if food_before is not None and food_before > 12.5:
            assert food_after == pytest.approx(food_before - 12.5)
        else:
            assert food_after is None, "Food bucket should disappear when emptied"

    @pytest.mark.parametrize("desc", ["", "    "])
    def test_blank_description_stored_as_null_and_row_still_listed(
        self, demo_client, app, lunch_id, token, desc
    ):
        response = demo_client.post(
            _edit_url(app, lunch_id),
            data=_form(token, amount="77.77", description=desc),
        )
        assert response.status_code == 302
        assert _expense_row(lunch_id)["description"] is None
        page = _text(demo_client.get(_profile_url(app)))
        assert "₹77.77" in page, "Row without description should still render"
        total, count = _total_and_count(page)
        assert count == "8"

    def test_forged_user_id_and_id_fields_ignored(
        self, demo_client, app, lunch_id, demo_id, user_b_id, token
    ):
        count_b = _count_expenses(user_b_id)
        other_id = _expense_id_by_description("Bus fare")
        before_other = _expense_row(other_id)
        response = demo_client.post(
            _edit_url(app, lunch_id),
            data=_form(token, amount="31", user_id=str(user_b_id), id=str(other_id)),
        )
        assert response.status_code == 302
        row = _expense_row(lunch_id)
        assert row["user_id"] == demo_id, "Expense must stay with the session user"
        assert row["amount"] == 31.0
        assert _count_expenses(user_b_id) == count_b
        assert (
            _expense_row(other_id) == before_other
        ), "Forged id must not redirect the update"

    def test_date_moved_to_last_month_changes_presets(
        self, demo_client, app, lunch_id, token
    ):
        today = date.today()
        first_this = today.replace(day=1)
        first_prev = _shift_month(today, -1)
        last_prev = first_this - timedelta(days=1)
        this_params = {"from": first_this.isoformat(), "to": today.isoformat()}
        last_params = {"from": first_prev.isoformat(), "to": last_prev.isoformat()}

        this_before = _text(demo_client.get(_profile_url(app, **this_params)))
        assert "Lunch" in this_before, "Seeded Lunch should start in this month"
        _, this_count_before = _total_and_count(this_before)

        moved = first_prev.replace(day=15).isoformat()
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form(token, date=moved, amount="12.50")
        )
        assert response.status_code == 302

        this_after = _text(demo_client.get(_profile_url(app, **this_params)))
        last_after = _text(demo_client.get(_profile_url(app, **last_params)))
        assert "Lunch" not in this_after, "Should leave 'This month'"
        assert "Lunch" in last_after, "Should appear under 'Last month'"
        _, this_count_after = _total_and_count(this_after)
        assert int(this_count_after) == int(this_count_before) - 1

    def test_past_date_accepted(self, demo_client, app, lunch_id, token):
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form(token, date="2020-05-06")
        )
        assert response.status_code == 302
        assert _expense_row(lunch_id)["date"] == "2020-05-06"

    def test_today_accepted_and_boundary_amounts(
        self, demo_client, app, lunch_id, token
    ):
        for amount in ("0.01", "1000000"):
            response = demo_client.post(
                _edit_url(app, lunch_id), data=_form(token, amount=amount)
            )
            assert response.status_code == 302, f"{amount} should be accepted"

    def test_unchanged_form_resubmit_succeeds(self, demo_client, app, lunch_id, token):
        before = _expense_row(lunch_id)
        response = demo_client.post(
            _edit_url(app, lunch_id),
            data=_form(token, amount="12.50", date=before["date"]),
        )
        assert response.status_code == 302
        assert _expense_row(lunch_id) == before

    def test_edit_not_visible_to_other_user(self, client, app, lunch_id, user_b_id):
        _login(client, DEMO["email"], DEMO["password"])
        tok = _get_token(client, app, lunch_id)
        client.post(
            _edit_url(app, lunch_id), data=_form(tok, description="A-private-note")
        )
        client.get("/logout")
        _login(client, USER_B["email"], USER_B["password"])
        page = _text(client.get(_profile_url(app)))
        assert "A-private-note" not in page


# --------------------------------------------------------------------------
# Invalid POST
# --------------------------------------------------------------------------
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
    def test_invalid_input_returns_400_with_message_and_row_unchanged(
        self, demo_client, app, lunch_id, token, override, message
    ):
        override = {
            k: (_tomorrow() if v == "FUTURE" else v) for k, v in override.items()
        }
        before = _expense_row(lunch_id)
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form(token, **override)
        )
        assert response.status_code == 400, f"Expected 400 for {override}"
        page = _text(response)
        assert _error_banner(page) == message
        assert 'role="alert"' in page
        assert _expense_row(lunch_id) == before, "DB row must be unchanged on error"

    def test_empty_form_after_valid_token_returns_400_not_500(
        self, demo_client, app, lunch_id, token
    ):
        before = _expense_row(lunch_id)
        response = demo_client.post(
            _edit_url(app, lunch_id), data={"csrf_token": token}
        )
        assert response.status_code == 400
        assert _error_banner(_text(response)) == ERR_AMOUNT
        assert _expense_row(lunch_id) == before

    def test_only_first_error_reported(self, demo_client, app, lunch_id, token):
        response = demo_client.post(
            _edit_url(app, lunch_id),
            data=_form(
                token,
                amount="abc",
                category="Crypto",
                date="bad",
                description="a" * 300,
            ),
        )
        page = _text(response)
        assert response.status_code == 400
        assert _error_banner(page) == ERR_AMOUNT
        for other in (ERR_CATEGORY, ERR_DATE, ERR_DESC):
            assert other not in page

    def test_sticky_values_after_failed_post(self, demo_client, app, lunch_id, token):
        response = demo_client.post(
            _edit_url(app, lunch_id),
            data=_form(
                token,
                amount="abc",
                category="Bills",
                date="2020-05-06",
                description="Keep me",
            ),
        )
        page = _text(response)
        assert response.status_code == 400
        assert _selected_option(page) == "Bills"
        assert 'value="2020-05-06"' in _input_tag(page, "date")
        assert "abc" in _input_tag(page, "amount")
        assert 'value="Keep me"' in _input_tag(page, "description")

    def test_sticky_values_not_overwritten_by_db_values(
        self, demo_client, app, lunch_id, token
    ):
        response = demo_client.post(
            _edit_url(app, lunch_id),
            data=_form(token, amount="33.5", date="2020-13-45", category="Health"),
        )
        page = _text(response)
        assert _error_banner(page) == ERR_DATE
        assert 'value="33.5"' in _input_tag(page, "amount")
        assert 'value="12.50"' not in _input_tag(page, "amount")
        assert _selected_option(page) == "Health"

    def test_rerender_form_still_posts_to_same_edit_url(
        self, demo_client, app, lunch_id, token
    ):
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form(token, amount="0")
        )
        assert f'action="{_edit_url(app, lunch_id)}"' in _text(response)

    def test_script_in_description_is_escaped(self, demo_client, app, lunch_id, token):
        payload = '"><script>alert(1)</script>'
        response = demo_client.post(
            _edit_url(app, lunch_id),
            data=_form(token, amount="bad", description=payload),
        )
        assert response.status_code == 400
        assert "<script>alert(1)</script>" not in _text(response)

    def test_forged_user_id_on_invalid_post_changes_nothing(
        self, demo_client, app, lunch_id, user_b_id, token
    ):
        before = _expense_row(lunch_id)
        response = demo_client.post(
            _edit_url(app, lunch_id),
            data=_form(token, amount="0", user_id=str(user_b_id)),
        )
        assert response.status_code == 400
        assert _expense_row(lunch_id) == before

    def test_deleted_mid_edit_returns_404(self, demo_client, app, lunch_id, token):
        conn = db.get_db()
        try:
            conn.execute("DELETE FROM expenses WHERE id = ?", (lunch_id,))
            conn.commit()
        finally:
            conn.close()
        response = demo_client.post(_edit_url(app, lunch_id), data=_form(token))
        assert response.status_code == 404
        assert _expense_row(lunch_id) is None, "Update must not resurrect the row"

    def test_sql_injection_in_description_stored_literally(
        self, demo_client, app, lunch_id, token
    ):
        payload = "'); DROP TABLE expenses;--"
        count = _count_expenses()
        response = demo_client.post(
            _edit_url(app, lunch_id), data=_form(token, description=payload)
        )
        assert response.status_code == 302
        assert _count_expenses() == count
        assert _expense_row(lunch_id)["description"] == payload


# --------------------------------------------------------------------------
# Profile edit links
# --------------------------------------------------------------------------
class TestProfileLinks:
    def test_every_row_has_edit_link_to_its_id(self, demo_client, app, demo_id):
        page = _text(demo_client.get(_profile_url(app)))
        hrefs = re.findall(r'<a\b[^>]*class="profile-edit-link"[^>]*>', page)
        hrefs += [] if hrefs else re.findall(r"<a\b[^>]*profile-edit-link[^>]*>", page)
        assert len(hrefs) == 8, "Expected one Edit link per transaction"
        found = {_attr(tag, "href") for tag in hrefs}
        expected = {
            _edit_url(app, row["id"]) for row in db.get_recent_expenses(demo_id)
        }
        assert found == expected

    def test_edit_cell_markup_and_label_text(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_profile_url(app)))
        m = re.search(
            r'<td class="profile-edit-col"><a href="%s"[^>]*>(.*?)</a></td>'
            % re.escape(_edit_url(app, lunch_id)),
            page,
            re.S,
        )
        assert m, "Edit cell for Lunch missing"
        assert "Edit" in m.group(1)

    def test_aria_label_uses_description_and_date(
        self, demo_client, app, demo_id, lunch_id
    ):
        row = db.get_expense_by_id(lunch_id, demo_id)
        page = _text(demo_client.get(_profile_url(app)))
        shown = date.fromisoformat(row["date"]).strftime("%d %b %Y")
        assert f'aria-label="Edit Lunch on {shown}"' in page

    def test_aria_label_falls_back_to_category_when_no_description(
        self, demo_client, app, demo_id, lunch_id
    ):
        db.update_expense(
            lunch_id, demo_id, 12.5, "Food", date.today().isoformat(), None
        )
        page = _text(demo_client.get(_profile_url(app)))
        shown = date.today().strftime("%d %b %Y")
        assert f'aria-label="Edit Food on {shown}"' in page

    def test_edit_links_use_the_row_id_not_position(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_profile_url(app)))
        assert f'href="{_edit_url(app, lunch_id)}"' in page

    def test_amount_cell_count_unchanged(self, demo_client, app):
        page = _text(demo_client.get(_profile_url(app)))
        assert len(re.findall(r'class="profile-num profile-amount"', page)) == 8

    def test_filtered_view_links_only_visible_rows(self, demo_client, app):
        page = _text(
            demo_client.get(
                _profile_url(app, **{"from": "2000-01-01", "to": "2000-01-02"})
            )
        )
        assert "profile-edit-link" not in page

    def test_other_user_profile_has_no_links_to_demo_expenses(
        self, client, app, user_b_id, lunch_id
    ):
        _login(client, USER_B["email"], USER_B["password"])
        page = _text(client.get(_profile_url(app)))
        assert _edit_url(app, lunch_id) not in page


# --------------------------------------------------------------------------
# Static checks and untouched stub
# --------------------------------------------------------------------------
class TestStaticHygiene:
    def test_app_py_contains_no_sql(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        assert not re.search(
            r"\b(SELECT|INSERT|UPDATE|DELETE)\b\s", source
        ), "SQL found in app.py"
        assert ".execute(" not in source, "app.py must not run queries"

    @pytest.mark.parametrize("func", ["get_expense_by_id", "update_expense"])
    def test_db_helpers_filter_by_user_id_with_static_sql(self, func):
        source = inspect.getsource(getattr(db, func))
        assert re.search(
            r"user_id\s*=\s*\?", source
        ), f"{func} must scope by user_id in SQL"
        assert re.search(r"id\s*=\s*\?", source)
        assert not re.search(
            r'\bf["\'][^"\']*(SELECT|UPDATE|WHERE)', source
        ), "No f-string SQL"
        assert "%s" not in source and ".format(" not in source

    def test_edit_template_hygiene(self):
        source = (ROOT / "templates" / "edit_expense.html").read_text(encoding="utf-8")
        assert "|safe" not in source.replace(" ", ""), "|safe is forbidden"
        assert "<style" not in source and "style=" not in source
        assert 'action="/' not in source and 'href="/' not in source
        assert "{% extends" in source and "base.html" in source
        assert "expense.css" in source

    def test_profile_css_edit_rules_exist_without_hex_colours(self):
        source = (ROOT / "static" / "css" / "profile.css").read_text(encoding="utf-8")
        for selector in (r"\.profile-edit-link", r"\.sr-only"):
            m = re.search(selector + r"[^{]*\{([^}]*)\}", source)
            assert m, f"{selector} rule missing"
            assert not re.search(
                r"#[0-9a-fA-F]{3,8}\b", m.group(1)
            ), "Hex colours are forbidden"

    def test_delete_route_is_still_a_stub(self, demo_client, app):
        response = demo_client.get(_url(app, "delete_expense", id=1))
        assert response.status_code == 200
        assert "Delete expense — coming in Step 9" in _text(response)

    def test_edit_route_registered_for_get_and_post_on_expense_id(self, app):
        rules = [r for r in app.url_map.iter_rules() if r.endpoint == "edit_expense"]
        assert rules, "edit_expense endpoint missing"
        methods = set().union(*(r.methods for r in rules))
        assert {"GET", "POST"} <= methods
        assert any("expense_id" in r.arguments for r in rules)
