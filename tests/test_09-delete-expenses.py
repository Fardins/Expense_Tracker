"""Tests for Step 9 - delete expenses (spec 09-delete-expenses).

Written from the spec and plan only. Uses the conftest `app` fixture (temp DB,
seeded demo user) and pytest-flask's `client`. Never imports `app` at module
level. Helpers are copied from test_08 rather than imported.
"""

import inspect
import re
from datetime import date
from pathlib import Path

import pytest
from flask import url_for

from database import db

DEMO = {"email": "demo@spendly.com", "password": "demo123"}
USER_B = {"name": "Other User", "email": "other@example.com", "password": "otherpass12"}

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


def _url(app, endpoint, **values):
    with app.test_request_context():
        return url_for(endpoint, **values)


def _delete_url(app, expense_id):
    return _url(app, "delete_expense", expense_id=expense_id)


def _profile_url(app, **params):
    return _url(app, "profile", **params)


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


def _ids_in_category(user_id, category):
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT id FROM expenses WHERE user_id = ? AND category = ?",
            (user_id, category),
        ).fetchall()
        return [r["id"] for r in rows]
    finally:
        conn.close()


def _all_ids(user_id):
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT id FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [r["id"] for r in rows]
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
    response = client.get(_delete_url(app, expense_id))
    assert response.status_code == 200, "Delete page must load to read the token"
    return _csrf_from_page(_text(response))


def _total_and_count(page):
    total = re.search(r"profile-total-spent[^>]*>\s*([^<]+)<", page)
    count = re.search(r"Transactions</p>\s*<p[^>]*>\s*(\d+)\s*<", page)
    return (
        total.group(1).strip() if total else None,
        count.group(1) if count else None,
    )


def _shown_date(iso):
    return date.fromisoformat(iso).strftime("%d %b %Y")


def _delete_links(page):
    return re.findall(r"<a\b[^>]*profile-delete-link[^>]*>", page)


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
# db helper
# --------------------------------------------------------------------------
class TestDbHelper:
    def test_delete_expense_row_deletes_and_returns_true(self, app, demo_id, lunch_id):
        count = _count_expenses()
        assert db.delete_expense_row(lunch_id, demo_id) is True
        assert _expense_row(lunch_id) is None
        assert _count_expenses() == count - 1

    def test_delete_expense_row_wrong_user_returns_false_and_keeps_row(
        self, app, user_b_id, lunch_id
    ):
        before = _expense_row(lunch_id)
        assert db.delete_expense_row(lunch_id, user_b_id) is False
        assert _expense_row(lunch_id) == before

    def test_delete_expense_row_missing_id_returns_false(self, app, demo_id):
        count = _count_expenses()
        assert db.delete_expense_row(999999, demo_id) is False
        assert _count_expenses() == count

    def test_delete_expense_row_twice_second_returns_false(
        self, app, demo_id, lunch_id
    ):
        assert db.delete_expense_row(lunch_id, demo_id) is True
        assert db.delete_expense_row(lunch_id, demo_id) is False

    def test_delete_expense_row_does_not_touch_other_rows(self, app, demo_id, lunch_id):
        other_id = _expense_id_by_description("Bus fare")
        before = _expense_row(other_id)
        db.delete_expense_row(lunch_id, demo_id)
        assert _expense_row(other_id) == before

    def test_get_expense_by_id_none_after_delete(self, app, demo_id, lunch_id):
        db.delete_expense_row(lunch_id, demo_id)
        assert db.get_expense_by_id(lunch_id, demo_id) is None


# --------------------------------------------------------------------------
# Access rules
# --------------------------------------------------------------------------
class TestAccess:
    def test_logged_out_get_redirects_to_login(self, client, app, lunch_id):
        response = client.get(_delete_url(app, lunch_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _expense_row(lunch_id) is not None

    def test_logged_out_post_redirects_and_row_still_exists(
        self, client, app, lunch_id
    ):
        before = _expense_row(lunch_id)
        response = client.post(_delete_url(app, lunch_id), data={"csrf_token": "x"})
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _expense_row(lunch_id) == before

    def test_logged_out_non_existent_id_redirects_not_404(self, client, app):
        for method in (client.get, client.post):
            response = method(_delete_url(app, 999999))
            assert response.status_code == 302
            assert "/login" in response.headers["Location"]

    def test_stale_session_get_clears_session_and_redirects(
        self, client, app, lunch_id
    ):
        with client.session_transaction() as sess:
            sess["user_id"] = 9999
        response = client.get(_delete_url(app, lunch_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        with client.session_transaction() as sess:
            assert "user_id" not in sess, "Stale session must be cleared"
        assert _expense_row(lunch_id) is not None

    def test_stale_session_post_clears_session_and_row_still_exists(
        self, client, app, lunch_id
    ):
        before = _expense_row(lunch_id)
        with client.session_transaction() as sess:
            sess["user_id"] = 9999
            sess["csrf_token"] = "tok"
        response = client.post(_delete_url(app, lunch_id), data={"csrf_token": "tok"})
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        with client.session_transaction() as sess:
            assert "user_id" not in sess
        assert _expense_row(lunch_id) == before

    @pytest.mark.parametrize("bad_id", ["999999", "abc", "0", "-1"])
    def test_unknown_or_non_integer_id_get_returns_404(self, demo_client, bad_id):
        response = demo_client.get(f"/expenses/{bad_id}/delete")
        assert response.status_code == 404

    def test_missing_id_post_with_valid_token_returns_404(
        self, demo_client, app, token
    ):
        before = _count_expenses()
        response = demo_client.post(
            _delete_url(app, 999999), data={"csrf_token": token}
        )
        assert response.status_code == 404
        assert _count_expenses() == before

    def test_missing_id_post_without_token_is_404_not_400(self, demo_client, app):
        response = demo_client.post(_delete_url(app, 999999), data={})
        assert response.status_code == 404, "Ownership check runs before CSRF"

    def test_other_users_expense_get_returns_404(
        self, client, app, lunch_id, user_b_id
    ):
        _login(client, USER_B["email"], USER_B["password"])
        response = client.get(_delete_url(app, lunch_id))
        assert response.status_code == 404, "Must be 404, never 403"
        assert "Lunch" not in _text(response), "No data from another user may leak"

    def test_other_users_expense_post_with_own_valid_token_returns_404(
        self, client, app, lunch_id, user_b_id
    ):
        before = _expense_row(lunch_id)
        _login(client, USER_B["email"], USER_B["password"])
        with client.session_transaction() as sess:
            sess["csrf_token"] = "tok"
        response = client.post(_delete_url(app, lunch_id), data={"csrf_token": "tok"})
        assert response.status_code == 404
        assert _expense_row(lunch_id) == before

    def test_other_users_expense_post_without_token_is_404_not_400(
        self, client, app, lunch_id, user_b_id
    ):
        before = _expense_row(lunch_id)
        _login(client, USER_B["email"], USER_B["password"])
        response = client.post(_delete_url(app, lunch_id), data={})
        assert response.status_code == 404
        assert _expense_row(lunch_id) == before

    def test_other_users_post_with_forged_user_id_still_404(
        self, client, app, lunch_id, demo_id, user_b_id
    ):
        before = _expense_row(lunch_id)
        _login(client, USER_B["email"], USER_B["password"])
        with client.session_transaction() as sess:
            sess["csrf_token"] = "tok"
        response = client.post(
            _delete_url(app, lunch_id),
            data={"csrf_token": "tok", "user_id": str(demo_id)},
        )
        assert response.status_code == 404
        assert _expense_row(lunch_id) == before

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_other_methods_return_405(self, demo_client, app, lunch_id, method):
        response = getattr(demo_client, method)(_delete_url(app, lunch_id))
        assert response.status_code == 405
        assert _expense_row(lunch_id) is not None

    def test_route_registered_for_get_and_post_on_expense_id(self, app):
        rules = [r for r in app.url_map.iter_rules() if r.endpoint == "delete_expense"]
        assert rules, "delete_expense endpoint missing"
        methods = set().union(*(r.methods for r in rules))
        assert {"GET", "POST"} <= methods
        assert any("expense_id" in r.arguments for r in rules)

    def test_url_matches_contract(self, app, lunch_id):
        assert _delete_url(app, lunch_id) == f"/expenses/{lunch_id}/delete"


# --------------------------------------------------------------------------
# GET confirmation page
# --------------------------------------------------------------------------
class TestConfirmationPage:
    def test_returns_200_with_title_and_heading(self, demo_client, app, lunch_id):
        response = demo_client.get(_delete_url(app, lunch_id))
        assert response.status_code == 200
        page = _text(response)
        title = re.search(r"<title>(.*?)</title>", page, re.S)
        assert title, "Title tag missing"
        assert title.group(1).strip() == "Delete expense — Spendly"
        assert "Delete expense" in page

    def test_shows_lunch_details(self, demo_client, app, lunch_id, demo_id):
        row = db.get_expense_by_id(lunch_id, demo_id)
        page = _text(demo_client.get(_delete_url(app, lunch_id)))
        assert _shown_date(row["date"]) in page, "Date must be 'DD Mon YYYY'"
        assert "Lunch" in page
        assert "Food" in page
        assert "₹12.50" in page

    def test_whole_number_amount_has_two_decimals(self, demo_client, app):
        pharmacy = _expense_id_by_description("Pharmacy")
        page = _text(demo_client.get(_delete_url(app, pharmacy)))
        assert "₹20.00" in page
        assert "Health" in page

    def test_null_description_falls_back_to_category(
        self, demo_client, app, demo_id, lunch_id
    ):
        db.update_expense(
            lunch_id, demo_id, 12.5, "Food", date.today().isoformat(), None
        )
        page = _text(demo_client.get(_delete_url(app, lunch_id)))
        assert "Food" in page
        assert not re.search(r">\s*None\s*<", page), "NULL must not render as None"

    def test_form_posts_to_delete_url_with_hidden_token_only(
        self, demo_client, app, lunch_id
    ):
        page = _text(demo_client.get(_delete_url(app, lunch_id)))
        form = re.search(r"<form\b[^>]*>(.*?)</form>", page, re.S)
        assert form, "Form missing"
        open_tag = re.search(r"<form\b[^>]*>", page).group(0).lower()
        assert 'method="post"' in open_tag
        assert f'action="{_delete_url(app, lunch_id)}"' in open_tag
        tag = _input_tag(page, "csrf_token")
        assert tag is not None and 'type="hidden"' in tag
        with demo_client.session_transaction() as sess:
            assert _attr(tag, "value") == sess["csrf_token"]
        names = re.findall(r"<input\b[^>]*name=\"([^\"]+)\"", form.group(1))
        assert names == ["csrf_token"], "Form must carry only the CSRF token"

    def test_cancel_link_and_danger_submit_button(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_delete_url(app, lunch_id)))
        assert "Cancel" in page
        assert f'href="{_profile_url(app)}"' in page, "Cancel must link to the profile"
        button = re.search(r"<button\b[^>]*>(.*?)</button>", page, re.S)
        assert button, "Submit button missing"
        tag = re.search(r"<button\b[^>]*>", page).group(0)
        assert "btn-danger" in tag
        assert "Delete expense" in re.sub(r"<[^>]+>", "", button.group(1))
        assert "submit" in tag or "type=" not in tag

    def test_has_warning_that_action_cannot_be_undone(self, demo_client, app, lunch_id):
        page = _text(demo_client.get(_delete_url(app, lunch_id))).lower()
        assert "undone" in page

    def test_token_is_stable_across_requests(self, demo_client, app, lunch_id):
        assert _get_token(demo_client, app, lunch_id) == _get_token(
            demo_client, app, lunch_id
        )

    def test_tokens_differ_between_sessions(self, app, lunch_id):
        c1 = app.test_client()
        c2 = app.test_client()
        _login(c1, DEMO["email"], DEMO["password"])
        _login(c2, DEMO["email"], DEMO["password"])
        assert _get_token(c1, app, lunch_id) != _get_token(c2, app, lunch_id)

    def test_repeated_get_never_deletes(self, demo_client, app, lunch_id):
        before = _expense_row(lunch_id)
        count = _count_expenses()
        for _ in range(5):
            assert demo_client.get(_delete_url(app, lunch_id)).status_code == 200
        assert _expense_row(lunch_id) == before
        assert _count_expenses() == count

    def test_description_is_escaped(self, demo_client, app, demo_id, lunch_id):
        payload = '"><script>alert(1)</script>'
        db.update_expense(
            lunch_id, demo_id, 12.5, "Food", date.today().isoformat(), payload
        )
        page = _text(demo_client.get(_delete_url(app, lunch_id)))
        assert "<script>alert(1)</script>" not in page
        assert "&lt;script&gt;" in page

    def test_cancel_returns_to_profile_with_expense_still_listed(
        self, demo_client, app, lunch_id
    ):
        page = _text(demo_client.get(_delete_url(app, lunch_id)))
        cancel = re.search(r'<a\b[^>]*href="([^"]+)"[^>]*>\s*Cancel\s*</a>', page)
        assert cancel, "Cancel link missing"
        response = demo_client.get(cancel.group(1))
        assert response.status_code == 200
        assert "Lunch" in _text(response)
        assert _expense_row(lunch_id) is not None


# --------------------------------------------------------------------------
# CSRF
# --------------------------------------------------------------------------
class TestCsrf:
    def test_valid_token_deletes(self, demo_client, app, lunch_id, token):
        response = demo_client.post(
            _delete_url(app, lunch_id), data={"csrf_token": token}
        )
        assert response.status_code == 302
        assert _expense_row(lunch_id) is None

    def test_missing_token_field_returns_400_and_row_remains(
        self, demo_client, app, lunch_id, token
    ):
        before = _expense_row(lunch_id)
        response = demo_client.post(_delete_url(app, lunch_id), data={})
        assert response.status_code == 400
        assert _expense_row(lunch_id) == before

    @pytest.mark.parametrize("bad", ["", "wrong-token", "é€漢字", " ", "A" * 500])
    def test_wrong_token_returns_400_and_row_remains(
        self, demo_client, app, lunch_id, token, bad
    ):
        before = _expense_row(lunch_id)
        response = demo_client.post(
            _delete_url(app, lunch_id), data={"csrf_token": bad}
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
        response = victim.post(_delete_url(app, lunch_id), data={"csrf_token": stolen})
        assert response.status_code == 400
        assert _expense_row(lunch_id) == before

    @pytest.mark.parametrize("submitted", ["", "anything", "é"])
    def test_no_session_token_returns_400(self, demo_client, app, lunch_id, submitted):
        with demo_client.session_transaction() as sess:
            sess.pop("csrf_token", None)
        before = _expense_row(lunch_id)
        response = demo_client.post(
            _delete_url(app, lunch_id), data={"csrf_token": submitted}
        )
        assert response.status_code == 400, "An empty session token must never match"
        assert _expense_row(lunch_id) == before

    def test_token_set_via_session_transaction_works(self, demo_client, app, lunch_id):
        with demo_client.session_transaction() as sess:
            sess["csrf_token"] = "fixed-token-for-test"
        response = demo_client.post(
            _delete_url(app, lunch_id), data={"csrf_token": "fixed-token-for-test"}
        )
        assert response.status_code == 302
        assert _expense_row(lunch_id) is None

    def test_login_rotates_token(self, client, app, lunch_id):
        _login(client, DEMO["email"], DEMO["password"])
        first = _get_token(client, app, lunch_id)
        client.get("/logout")
        _login(client, DEMO["email"], DEMO["password"])
        assert _get_token(client, app, lunch_id) != first

    def test_token_from_before_logout_cannot_delete_after_relogin(
        self, client, app, lunch_id
    ):
        _login(client, DEMO["email"], DEMO["password"])
        old = _get_token(client, app, lunch_id)
        client.get("/logout")
        _login(client, DEMO["email"], DEMO["password"])
        response = client.post(_delete_url(app, lunch_id), data={"csrf_token": old})
        assert response.status_code == 400
        assert _expense_row(lunch_id) is not None


# --------------------------------------------------------------------------
# Valid POST
# --------------------------------------------------------------------------
class TestValidPost:
    def test_definition_of_done_flow(self, demo_client, app, lunch_id, token):
        before_page = _text(demo_client.get(_profile_url(app)))
        before_total, before_count = _total_and_count(before_page)
        assert before_total == "₹222.19" and before_count == "8"
        food_before = _category_amount_on_page(before_page, "Food")
        assert food_before is not None

        response = demo_client.post(
            _delete_url(app, lunch_id), data={"csrf_token": token}
        )
        assert response.status_code == 302, "Success must redirect (PRG)"
        assert response.headers["Location"].endswith(_profile_url(app))

        page = _text(demo_client.get(_profile_url(app)))
        total, count = _total_and_count(page)
        assert total == "₹209.69", "Total should drop by 12.50"
        assert count == "7", "Transaction count must drop by 1"
        assert "Lunch" not in page, "Lunch row should be gone"
        food_after = _category_amount_on_page(page, "Food")
        if food_before > 12.5:
            assert food_after == pytest.approx(food_before - 12.5)
        else:
            assert food_after is None

    def test_success_response_is_not_a_rendered_page(
        self, demo_client, app, lunch_id, token
    ):
        response = demo_client.post(
            _delete_url(app, lunch_id), data={"csrf_token": token}
        )
        assert response.status_code == 302
        assert "Delete expense" not in _text(response)

    def test_redirect_followed_lands_on_profile(
        self, demo_client, app, lunch_id, token
    ):
        response = demo_client.post(
            _delete_url(app, lunch_id),
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Recent transactions" in _text(response)

    def test_only_target_row_deleted(self, demo_client, app, demo_id, lunch_id, token):
        others = {i: _expense_row(i) for i in _all_ids(demo_id) if i != lunch_id}
        demo_client.post(_delete_url(app, lunch_id), data={"csrf_token": token})
        assert _expense_row(lunch_id) is None
        assert _count_expenses(demo_id) == 7
        for i, row in others.items():
            assert _expense_row(i) == row

    def test_other_users_rows_unaffected(
        self, demo_client, app, lunch_id, user_b_id, token
    ):
        count_b = _count_expenses(user_b_id)
        demo_client.post(_delete_url(app, lunch_id), data={"csrf_token": token})
        assert _count_expenses(user_b_id) == count_b

    def test_deleting_last_expense_in_category_removes_it_from_breakdown(
        self, demo_client, app, demo_id
    ):
        page = _text(demo_client.get(_profile_url(app)))
        assert _category_amount_on_page(page, "Food") is not None
        ids = _ids_in_category(demo_id, "Food")
        assert ids, "Seed data should contain Food expenses"
        for expense_id in ids:
            tok = _get_token(demo_client, app, expense_id)
            response = demo_client.post(
                _delete_url(app, expense_id), data={"csrf_token": tok}
            )
            assert response.status_code == 302
        page = _text(demo_client.get(_profile_url(app)))
        assert _category_amount_on_page(page, "Food") is None
        assert _ids_in_category(demo_id, "Food") == []

    def test_deleting_every_expense_shows_empty_state_without_errors(
        self, demo_client, app, demo_id
    ):
        for expense_id in _all_ids(demo_id):
            tok = _get_token(demo_client, app, expense_id)
            response = demo_client.post(
                _delete_url(app, expense_id), data={"csrf_token": tok}
            )
            assert response.status_code == 302
        assert _count_expenses(demo_id) == 0
        response = demo_client.get(_profile_url(app))
        assert response.status_code == 200
        page = _text(response)
        assert _delete_links(page) == [], "No rows means no delete links"
        assert "Lunch" not in page
        _, count = _total_and_count(page)
        assert count in (None, "0")

    def test_forged_user_id_and_id_fields_ignored(
        self, demo_client, app, lunch_id, demo_id, user_b_id, token
    ):
        other_id = _expense_id_by_description("Bus fare")
        before_other = _expense_row(other_id)
        count_b = _count_expenses(user_b_id)
        response = demo_client.post(
            _delete_url(app, lunch_id),
            data={
                "csrf_token": token,
                "user_id": str(user_b_id),
                "id": str(other_id),
                "expense_id": str(other_id),
            },
        )
        assert response.status_code == 302
        assert _expense_row(lunch_id) is None
        assert _expense_row(other_id) == before_other, "Forged id must be ignored"
        assert _count_expenses(user_b_id) == count_b
        assert _count_expenses(demo_id) == 7

    def test_extra_form_fields_do_not_break_delete(
        self, demo_client, app, lunch_id, token
    ):
        response = demo_client.post(
            _delete_url(app, lunch_id),
            data={"csrf_token": token, "amount": "abc", "category": "Nope"},
        )
        assert response.status_code == 302
        assert _expense_row(lunch_id) is None

    def test_deleted_from_other_users_view_has_no_effect_on_them(
        self, client, app, lunch_id, user_b_id
    ):
        _login(client, DEMO["email"], DEMO["password"])
        tok = _get_token(client, app, lunch_id)
        client.post(_delete_url(app, lunch_id), data={"csrf_token": tok})
        client.get("/logout")
        _login(client, USER_B["email"], USER_B["password"])
        assert client.get(_profile_url(app)).status_code == 200


# --------------------------------------------------------------------------
# Double submit and deleted mid-flow
# --------------------------------------------------------------------------
class TestDoubleSubmit:
    def test_second_post_returns_404_and_no_other_row_affected(
        self, demo_client, app, demo_id, lunch_id, token
    ):
        first = demo_client.post(_delete_url(app, lunch_id), data={"csrf_token": token})
        assert first.status_code == 302
        remaining = {i: _expense_row(i) for i in _all_ids(demo_id)}
        second = demo_client.post(
            _delete_url(app, lunch_id), data={"csrf_token": token}
        )
        assert second.status_code == 404
        assert {i: _expense_row(i) for i in _all_ids(demo_id)} == remaining

    def test_get_after_delete_returns_404(self, demo_client, app, lunch_id, token):
        demo_client.post(_delete_url(app, lunch_id), data={"csrf_token": token})
        assert demo_client.get(_delete_url(app, lunch_id)).status_code == 404

    def test_row_removed_elsewhere_before_post_returns_404(
        self, demo_client, app, demo_id, lunch_id, token
    ):
        assert db.delete_expense_row(lunch_id, demo_id) is True
        response = demo_client.post(
            _delete_url(app, lunch_id), data={"csrf_token": token}
        )
        assert response.status_code == 404


# --------------------------------------------------------------------------
# Profile delete links
# --------------------------------------------------------------------------
class TestProfileLinks:
    def test_every_row_has_delete_link_to_its_id(self, demo_client, app, demo_id):
        page = _text(demo_client.get(_profile_url(app)))
        tags = _delete_links(page)
        assert len(tags) == 8, "Expected one Delete link per transaction"
        found = {_attr(tag, "href") for tag in tags}
        expected = {
            _delete_url(app, row["id"]) for row in db.get_recent_expenses(demo_id)
        }
        assert found == expected

    def test_delete_link_is_an_anchor_with_class_and_text(
        self, demo_client, app, lunch_id
    ):
        page = _text(demo_client.get(_profile_url(app)))
        m = re.search(
            r'<a\b[^>]*href="%s"[^>]*class="profile-delete-link"[^>]*>(.*?)</a>'
            % re.escape(_delete_url(app, lunch_id)),
            page,
            re.S,
        ) or re.search(
            r'<a\b[^>]*class="profile-delete-link"[^>]*href="%s"[^>]*>(.*?)</a>'
            % re.escape(_delete_url(app, lunch_id)),
            page,
            re.S,
        )
        assert m, "Delete link for Lunch missing"
        assert "Delete" in re.sub(r"<[^>]+>", "", m.group(1))

    def test_delete_link_follows_edit_link_in_same_cell(
        self, demo_client, app, lunch_id
    ):
        page = _text(demo_client.get(_profile_url(app)))
        cells = re.findall(r'<td class="profile-edit-col">(.*?)</td>', page, re.S)
        lunch_cells = [c for c in cells if f'href="{_delete_url(app, lunch_id)}"' in c]
        assert len(lunch_cells) == 1
        content = lunch_cells[0]
        edit_pos = content.find("profile-edit-link")
        delete_pos = content.find("profile-delete-link")
        assert edit_pos != -1 and delete_pos != -1
        assert edit_pos < delete_pos, "Delete must come after Edit"

    def test_aria_label_uses_description_and_date(
        self, demo_client, app, demo_id, lunch_id
    ):
        row = db.get_expense_by_id(lunch_id, demo_id)
        page = _text(demo_client.get(_profile_url(app)))
        assert f'aria-label="Delete Lunch on {_shown_date(row["date"])}"' in page

    def test_aria_label_falls_back_to_category_when_no_description(
        self, demo_client, app, demo_id, lunch_id
    ):
        db.update_expense(
            lunch_id, demo_id, 12.5, "Food", date.today().isoformat(), None
        )
        page = _text(demo_client.get(_profile_url(app)))
        shown = date.today().strftime("%d %b %Y")
        assert f'aria-label="Delete Food on {shown}"' in page

    def test_edit_links_still_present(self, demo_client, app, demo_id):
        page = _text(demo_client.get(_profile_url(app)))
        assert len(re.findall(r"<a\b[^>]*profile-edit-link[^>]*>", page)) == 8

    def test_amount_cell_count_unchanged(self, demo_client, app):
        page = _text(demo_client.get(_profile_url(app)))
        assert len(re.findall(r'class="profile-num profile-amount"', page)) == 8

    def test_filtered_view_links_only_visible_rows(self, demo_client, app):
        page = _text(
            demo_client.get(
                _profile_url(app, **{"from": "2000-01-01", "to": "2000-01-02"})
            )
        )
        assert "profile-delete-link" not in page

    def test_other_user_profile_has_no_links_to_demo_expenses(
        self, client, app, user_b_id, lunch_id
    ):
        _login(client, USER_B["email"], USER_B["password"])
        page = _text(client.get(_profile_url(app)))
        assert _delete_url(app, lunch_id) not in page

    def test_clicking_delete_link_opens_confirmation_page(
        self, demo_client, app, lunch_id
    ):
        page = _text(demo_client.get(_profile_url(app)))
        tag = next(t for t in _delete_links(page) if _delete_url(app, lunch_id) in t)
        response = demo_client.get(_attr(tag, "href"))
        assert response.status_code == 200
        assert "₹12.50" in _text(response)


# --------------------------------------------------------------------------
# Static checks
# --------------------------------------------------------------------------
class TestStaticHygiene:
    def test_app_py_contains_no_delete_sql(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        assert "DELETE FROM" not in source, "SQL found in app.py"
        assert not re.search(
            r"\b(SELECT|INSERT|UPDATE|DELETE)\b\s", source
        ), "SQL found in app.py"
        assert ".execute(" not in source, "app.py must not run queries"

    def test_delete_expense_row_scopes_by_user_id_with_static_sql(self):
        source = inspect.getsource(db.delete_expense_row)
        assert re.search(r"DELETE FROM expenses", source)
        assert re.search(r"user_id\s*=\s*\?", source), "Must scope by user_id in SQL"
        assert re.search(r"\bid\s*=\s*\?", source)
        assert not re.search(
            r'\bf["\'][^"\']*(DELETE|WHERE)', source
        ), "No f-string SQL"
        assert "%s" not in source and ".format(" not in source

    def test_delete_template_hygiene(self):
        source = (ROOT / "templates" / "delete_expense.html").read_text(
            encoding="utf-8"
        )
        assert "|safe" not in source.replace(" ", ""), "|safe is forbidden"
        assert "<style" not in source and "style=" not in source
        assert 'action="/' not in source and 'href="/' not in source
        assert "{% extends" in source and "base.html" in source
        assert "expense.css" in source
        assert "confirm(" not in source and "<script" not in source

    def test_profile_template_has_no_hardcoded_delete_url(self):
        source = (ROOT / "templates" / "profile.html").read_text(encoding="utf-8")
        assert "profile-delete-link" in source
        assert (
            "url_for('delete_expense'" in source or 'url_for("delete_expense"' in source
        )
        assert not re.search(r'href="/expenses', source)

    @pytest.mark.parametrize(
        "css_file,selector",
        [
            ("expense.css", r"\.btn-danger"),
            ("profile.css", r"\.profile-delete-link"),
        ],
    )
    def test_css_rules_exist_without_hex_colours(self, css_file, selector):
        source = (ROOT / "static" / "css" / css_file).read_text(encoding="utf-8")
        rules = re.findall(selector + r"[^{}]*\{([^}]*)\}", source)
        assert rules, f"{selector} rule missing in {css_file}"
        for body in rules:
            assert not re.search(
                r"#[0-9a-fA-F]{3,8}\b", body
            ), "Hex colours are forbidden"
