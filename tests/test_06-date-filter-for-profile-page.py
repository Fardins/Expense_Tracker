"""Tests for Step 6 - date filter on /profile (spec 06-date-filter-for-profile-page).

Written from the spec only. Fixed-date (2020) expenses are inserted for a
dedicated user so inclusive bounds can be tested deterministically; the seeded
demo user (all expenses in the current month) is used for preset tests.
"""
import calendar
import html as html_lib
import re
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from flask import url_for

from database import db

DEMO = {"email": "demo@spendly.com", "password": "demo123"}
USER_A = {"name": "Filter User", "email": "filter@example.com", "password": "filterpass1"}
USER_B = {"name": "Other User", "email": "other@example.com", "password": "otherpass12"}

# (amount, category, date, description) for USER_A. All in 2020.
USER_A_EXPENSES = [
    (10.00, "Food", "2020-01-10", "tx-jan10"),
    (20.00, "Bills", "2020-01-15", "tx-jan15"),
    (30.00, "Food", "2020-01-20", "tx-jan20"),
    (5.00, "Transport", "2020-02-01", "tx-feb01"),
]
USER_A_ALL_TOTAL = "₹65.00"

PRESET_LABELS = ["All time", "This month", "Last month", "Last 3 months"]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _insert_expenses(user_id, rows):
    conn = db.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [(user_id, a, c, d, desc) for a, c, d, desc in rows],
        )
        conn.commit()
    finally:
        conn.close()


def _login(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


def _profile_url(app, **params):
    with app.test_request_context():
        return url_for("profile", **params)


def _get(client, app, **params):
    return client.get(_profile_url(app, **params))


def _text(response):
    return response.get_data(as_text=True)


def _snippet(page, css_class):
    """Text (tags stripped) of ~200 chars following the element with css_class."""
    m = re.search(
        r'class="[^"]*\b' + re.escape(css_class) + r'\b[^"]*"[^>]*>(.{0,200})',
        page,
        re.S,
    )
    assert m, f"Element with class {css_class!r} not found"
    return re.sub(r"<[^>]+>", " ", m.group(1))


def _total_spent(page):
    return _snippet(page, "profile-total-spent")


def _top_category(page):
    return _snippet(page, "profile-top-category")


def _anchors(page):
    """Return list of (attribute_string, inner_text, href) for every <a>."""
    out = []
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", page, re.S):
        attrs, inner = m.group(1), m.group(2)
        href_m = re.search(r'href="([^"]*)"', attrs)
        href = html_lib.unescape(href_m.group(1)) if href_m else None
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", inner)).strip()
        out.append((attrs, text, href))
    return out


def _preset_anchors(page):
    return {text: (attrs, href) for attrs, text, href in _anchors(page) if text in PRESET_LABELS}


def _input_tag(page, name):
    for m in re.finditer(r"<input\b[^>]*>", page):
        tag = m.group(0)
        if re.search(r'name="%s"' % re.escape(name), tag):
            return tag
    return None


def _query(href):
    return {k: v[0] for k, v in parse_qs(urlparse(href).query).items()}


def _shift_month(d, delta):
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def _expected_presets(today):
    first_this = today.replace(day=1)
    first_prev = _shift_month(today, -1)
    last_prev = first_prev.replace(day=calendar.monthrange(first_prev.year, first_prev.month)[1])
    first_3 = _shift_month(today, -2)
    return {
        "All time": {},
        "This month": {"from": first_this.isoformat(), "to": today.isoformat()},
        "Last month": {"from": first_prev.isoformat(), "to": last_prev.isoformat()},
        "Last 3 months": {"from": first_3.isoformat(), "to": today.isoformat()},
    }


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def user_a_id(app):
    uid = db.create_user(USER_A["name"], USER_A["email"], USER_A["password"])
    _insert_expenses(uid, USER_A_EXPENSES)
    return uid


@pytest.fixture
def user_a_client(client, user_a_id):
    _login(client, USER_A["email"], USER_A["password"])
    return client


@pytest.fixture
def demo_client(client):
    _login(client, DEMO["email"], DEMO["password"])
    return client


@pytest.fixture
def empty_user_client(client):
    db.create_user("Empty User", "empty@example.com", "emptypass12")
    _login(client, "empty@example.com", "emptypass12")
    return client


# --------------------------------------------------------------------------
# Auth guard
# --------------------------------------------------------------------------
class TestAuthGuard:
    def test_logged_out_filtered_profile_redirects_to_login(self, client, app):
        response = _get(client, app, **{"from": "2020-01-01", "to": "2020-12-31"})
        assert response.status_code == 302, "Logged-out filtered visit must redirect"
        assert "/login" in response.headers["Location"], "Must redirect to /login"

    def test_logged_out_unfiltered_profile_redirects_to_login(self, client, app):
        response = client.get(_profile_url(app))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------------
# No params == Step 5 behaviour
# --------------------------------------------------------------------------
class TestNoFilter:
    def test_no_params_shows_all_time_demo_numbers(self, demo_client, app):
        response = _get(demo_client, app)
        page = _text(response)
        assert response.status_code == 200
        assert "₹222.19" in _total_spent(page), "All-time total should be ₹222.19"
        assert "Bills" in _top_category(page), "Top category should be Bills"
        assert "Lunch" in page and "Groceries" in page, "Seeded transactions should show"

    def test_no_params_shows_no_error_and_all_time_caption(self, demo_client, app):
        page = _text(_get(demo_client, app))
        assert "profile-filter-error" not in page, "No error line without a filter problem"
        assert "Invalid date" not in page
        assert "Showing all time" in page, "Caption should say 'Showing all time'"

    def test_no_params_all_time_preset_active(self, demo_client, app):
        page = _text(_get(demo_client, app))
        active = [t for a, t, _ in _anchors(page) if "profile-filter-preset--active" in a]
        assert active == ["All time"], f"Only 'All time' should be active, got {active}"

    def test_empty_params_treated_as_missing(self, demo_client, app):
        response = _get(demo_client, app, **{"from": "", "to": ""})
        page = _text(response)
        assert response.status_code == 200
        assert "profile-filter-error" not in page, "Empty strings are missing, not errors"
        assert "₹222.19" in _total_spent(page)

    def test_no_filter_does_not_show_in_this_period_messages(self, empty_user_client, app):
        page = _text(_get(empty_user_client, app))
        assert "No transactions in this period." not in page
        assert "No spending in this period." not in page


# --------------------------------------------------------------------------
# Filter bar markup
# --------------------------------------------------------------------------
class TestFilterBar:
    def test_filter_section_present(self, demo_client, app):
        page = _text(_get(demo_client, app))
        assert 'aria-label="Date filter"' in page, "Filter section needs aria-label"
        assert "profile-filter" in page

    def test_four_presets_present(self, demo_client, app):
        presets = _preset_anchors(_text(_get(demo_client, app)))
        assert set(presets) == set(PRESET_LABELS), f"Expected 4 presets, got {set(presets)}"

    def test_form_is_get_to_profile_with_two_date_inputs_and_apply(self, demo_client, app):
        page = _text(_get(demo_client, app))
        form = re.search(r"<form\b[^>]*>", page[page.find("profile-filter"):])
        assert form, "Filter form missing"
        tag = form.group(0).lower()
        assert 'method="get"' in tag, "Form must use GET"
        assert 'action="%s"' % _profile_url(app) in tag, "Form action must be the profile URL"
        for name in ("from", "to"):
            inp = _input_tag(page, name)
            assert inp is not None, f"Missing input named {name!r}"
            assert 'type="date"' in inp, f"Input {name!r} must be type=date"
        assert "Apply" in page, "Apply button missing"

    def test_preset_hrefs_match_spec_ranges(self, demo_client, app):
        presets = _preset_anchors(_text(_get(demo_client, app)))
        expected = _expected_presets(date.today())
        for label, params in expected.items():
            href = presets[label][1]
            assert urlparse(href).path == _profile_url(app), f"{label} must link to profile"
            assert _query(href) == params, f"{label}: expected {params}, got {_query(href)}"

    def test_clear_link_hidden_without_filter(self, demo_client, app):
        anchors = _anchors(_text(_get(demo_client, app)))
        assert not [a for a in anchors if a[1] == "Clear"], "Clear shown with no filter"

    def test_clear_link_shown_with_filter_and_returns_to_bare_profile(self, demo_client, app):
        page = _text(_get(demo_client, app, **{"from": "2020-01-01"}))
        clear = [a for a in _anchors(page) if a[1] == "Clear"]
        assert clear, "Clear link expected when filter active"
        assert clear[0][2] == _profile_url(app), "Clear must link to /profile without params"


# --------------------------------------------------------------------------
# Presets behave correctly against data
# --------------------------------------------------------------------------
class TestPresets:
    def test_this_month_preset_includes_all_seeded_demo_expenses(self, demo_client, app):
        params = _expected_presets(date.today())["This month"]
        page = _text(_get(demo_client, app, **params))
        assert "₹222.19" in _total_spent(page)
        assert "Bills" in _top_category(page)

    def test_last_3_months_preset_includes_current_month_data(self, demo_client, app):
        params = _expected_presets(date.today())["Last 3 months"]
        page = _text(_get(demo_client, app, **params))
        assert "₹222.19" in _total_spent(page)

    def test_last_month_preset_excludes_current_month_data(self, demo_client, app):
        params = _expected_presets(date.today())["Last month"]
        response = _get(demo_client, app, **params)
        page = _text(response)
        assert response.status_code == 200
        assert "₹0.00" in _total_spent(page), "Demo has nothing last month"
        assert "Lunch" not in page

    @pytest.mark.parametrize("label", PRESET_LABELS)
    def test_following_preset_link_marks_exactly_that_preset_active(self, demo_client, app, label):
        href = _preset_anchors(_text(_get(demo_client, app)))[label][1]
        page = _text(demo_client.get(href))
        active = [(a, t) for a, t, _ in _anchors(page) if "profile-filter-preset--active" in a]
        assert [t for _, t in active] == [label], f"Expected only {label!r} active, got {active}"
        assert 'aria-current="true"' in active[0][0], "Active preset needs aria-current=true"

    def test_custom_range_marks_no_preset_active(self, demo_client, app):
        page = _text(_get(demo_client, app, **{"from": "2020-01-10", "to": "2020-01-20"}))
        assert "profile-filter-preset--active" not in page, "Custom range: no active preset"
        assert 'aria-current="true"' not in page

    def test_inactive_presets_have_no_aria_current(self, demo_client, app):
        page = _text(_get(demo_client, app))
        presets = _preset_anchors(page)
        for label in PRESET_LABELS[1:]:
            assert "aria-current" not in presets[label][0], f"{label} should not be current"


# --------------------------------------------------------------------------
# Filtering correctness (inclusive bounds, one-sided, per-section)
# --------------------------------------------------------------------------
class TestFilterCorrectness:
    def test_unfiltered_includes_all_user_a_expenses(self, user_a_client, app):
        page = _text(_get(user_a_client, app))
        assert USER_A_ALL_TOTAL in _total_spent(page)
        for _, _, _, desc in USER_A_EXPENSES:
            assert desc in page, f"{desc} should be visible all-time"

    def test_range_is_inclusive_on_both_ends(self, user_a_client, app):
        page = _text(_get(user_a_client, app, **{"from": "2020-01-10", "to": "2020-01-20"}))
        assert "tx-jan10" in page, "Expense on 'from' date must be included"
        assert "tx-jan20" in page, "Expense on 'to' date must be included"
        assert "tx-jan15" in page
        assert "tx-feb01" not in page, "Expense after 'to' must be excluded"
        assert "₹60.00" in _total_spent(page)

    def test_range_excludes_before_from_and_after_to(self, user_a_client, app):
        page = _text(_get(user_a_client, app, **{"from": "2020-01-11", "to": "2020-01-19"}))
        assert "tx-jan10" not in page, "Day before 'from' must be excluded"
        assert "tx-jan20" not in page, "Day after 'to' must be excluded"
        assert "tx-jan15" in page
        assert "₹20.00" in _total_spent(page)
        assert "Bills" in _top_category(page)

    def test_single_day_range_from_equals_to(self, user_a_client, app):
        response = _get(user_a_client, app, **{"from": "2020-01-15", "to": "2020-01-15"})
        page = _text(response)
        assert response.status_code == 200
        assert "profile-filter-error" not in page, "from == to is valid"
        assert "tx-jan15" in page and "tx-jan10" not in page and "tx-jan20" not in page
        assert "₹20.00" in _total_spent(page)

    def test_only_from_filters_on_or_after(self, user_a_client, app):
        page = _text(_get(user_a_client, app, **{"from": "2020-01-20"}))
        assert "tx-jan20" in page and "tx-feb01" in page
        assert "tx-jan10" not in page and "tx-jan15" not in page
        assert "₹35.00" in _total_spent(page)

    def test_only_to_filters_on_or_before(self, user_a_client, app):
        page = _text(_get(user_a_client, app, **{"to": "2020-01-10"}))
        assert "tx-jan10" in page
        assert "tx-jan15" not in page and "tx-feb01" not in page
        assert "₹10.00" in _total_spent(page)

    def test_top_category_reflects_filtered_range(self, user_a_client, app):
        page = _text(_get(user_a_client, app, **{"from": "2020-01-01", "to": "2020-01-31"}))
        assert "Food" in _top_category(page), "Food (40) beats Bills (20) in January"
        assert "₹40.00" in page, "Food category amount should be ₹40.00"

    def test_categories_section_uses_same_range(self, user_a_client, app):
        page = _text(_get(user_a_client, app, **{"from": "2020-02-01", "to": "2020-02-28"}))
        assert "Transport" in page
        assert "₹5.00" in _total_spent(page)
        assert "tx-jan10" not in page

    def test_range_with_no_data_shows_zero_state(self, user_a_client, app):
        response = _get(user_a_client, app, **{"from": "2021-01-01", "to": "2021-12-31"})
        page = _text(response)
        assert response.status_code == 200
        assert "₹0.00" in _total_spent(page), "Total should be ₹0.00"
        assert "—" in _top_category(page), "Top category should be an em dash"
        assert "No transactions in this period." in page
        assert "No spending in this period." in page

    def test_caption_for_custom_range(self, user_a_client, app):
        page = _text(_get(user_a_client, app, **{"from": "2020-01-10", "to": "2020-01-20"}))
        assert "Showing 10 Jan 2020 – 20 Jan 2020" in page, "Caption should format the range"

    def test_inputs_prefilled_with_active_values(self, user_a_client, app):
        page = _text(_get(user_a_client, app, **{"from": "2020-01-10", "to": "2020-01-20"}))
        assert 'value="2020-01-10"' in _input_tag(page, "from"), "'from' input not prefilled"
        assert 'value="2020-01-20"' in _input_tag(page, "to"), "'to' input not prefilled"

    def test_inputs_not_prefilled_without_filter(self, user_a_client, app):
        page = _text(_get(user_a_client, app))
        for name in ("from", "to"):
            tag = _input_tag(page, name)
            assert not re.search(r'value="[^"]+"', tag), f"{name!r} should be empty by default"


# --------------------------------------------------------------------------
# Validation errors
# --------------------------------------------------------------------------
class TestValidation:
    @pytest.mark.parametrize(
        "bad",
        [
            "not-a-date",
            "2020-13-01",
            "2020-02-30",
            "01/10/2020",
            "'; DROP TABLE expenses;--",
            '"><script>alert(1)</script>',
        ],
    )
    @pytest.mark.parametrize("param", ["from", "to"])
    def test_invalid_date_renders_200_with_error(self, user_a_client, app, param, bad):
        response = _get(user_a_client, app, **{param: bad})
        page = _text(response)
        assert response.status_code == 200, "Invalid dates must never 500"
        assert "Invalid date" in page, "Inline invalid-date error expected"
        assert "profile-filter-error" in page and 'role="alert"' in page

    @pytest.mark.parametrize("param", ["from", "to"])
    def test_invalid_date_falls_back_to_all_time_data(self, user_a_client, app, param):
        page = _text(_get(user_a_client, app, **{param: "not-a-date"}))
        assert USER_A_ALL_TOTAL in _total_spent(page), "Invalid single value => all time"
        for _, _, _, desc in USER_A_EXPENSES:
            assert desc in page

    def test_invalid_from_with_valid_to_still_200_with_error(self, user_a_client, app):
        response = _get(user_a_client, app, **{"from": "garbage", "to": "2020-01-10"})
        assert response.status_code == 200
        assert "Invalid date" in _text(response)

    def test_invalid_input_not_echoed_unescaped(self, user_a_client, app):
        page = _text(_get(user_a_client, app, **{"from": '"><script>alert(1)</script>'}))
        assert "<script>alert(1)</script>" not in page, "Query value must be escaped"

    def test_invalid_input_does_not_damage_database(self, user_a_client, app, user_a_id):
        _get(user_a_client, app, **{"from": "'; DROP TABLE expenses;--"})
        summary = db.get_expense_summary(user_a_id)
        assert summary["count"] == len(USER_A_EXPENSES), "Expenses table must be intact"

    def test_reversed_range_shows_error_and_all_time(self, user_a_client, app):
        response = _get(user_a_client, app, **{"from": "2020-02-01", "to": "2020-01-01"})
        page = _text(response)
        assert response.status_code == 200
        assert "Start date must be on or before end date." in page
        assert USER_A_ALL_TOTAL in _total_spent(page), "Both values ignored => all time"
        for _, _, _, desc in USER_A_EXPENSES:
            assert desc in page

    def test_reversed_range_from_spec_example_for_demo(self, demo_client, app):
        response = _get(demo_client, app, **{"from": "2026-10-31", "to": "2026-10-01"})
        page = _text(response)
        assert response.status_code == 200
        assert "Start date must be on or before end date" in page
        assert "₹222.19" in _total_spent(page)

    def test_reversed_range_marks_all_time_active(self, user_a_client, app):
        page = _text(_get(user_a_client, app, **{"from": "2020-02-01", "to": "2020-01-01"}))
        active = [t for a, t, _ in _anchors(page) if "profile-filter-preset--active" in a]
        assert active in (["All time"], []), "Ignored range must not highlight a date preset"
        assert "Showing all time" in page


# --------------------------------------------------------------------------
# Per-user isolation
# --------------------------------------------------------------------------
class TestUserIsolation:
    def test_filtered_view_excludes_other_users_expenses(self, user_a_client, app):
        # Range covering the demo user's current-month data as well as nothing of A's.
        params = _expected_presets(date.today())["This month"]
        page = _text(_get(user_a_client, app, **params))
        assert "Lunch" not in page and "Groceries" not in page, "Demo data leaked"
        assert "₹0.00" in _total_spent(page)

    def test_demo_filtered_view_excludes_user_a_expenses(self, demo_client, app, user_a_id):
        page = _text(_get(demo_client, app, **{"from": "2020-01-01", "to": "2020-12-31"}))
        assert "tx-jan10" not in page, "User A data leaked into demo view"
        assert "₹0.00" in _total_spent(page)

    def test_user_id_query_param_is_ignored(self, user_a_client, app):
        conn = db.get_db()
        try:
            demo_id = conn.execute(
                "SELECT id FROM users WHERE email = ?", (DEMO["email"],)
            ).fetchone()["id"]
        finally:
            conn.close()
        page = _text(_get(user_a_client, app, user_id=demo_id))
        assert "Lunch" not in page, "user_id must come from session only"
        assert USER_A_ALL_TOTAL in _total_spent(page)

    def test_two_users_same_dates_get_own_totals(self, client, app, user_a_id):
        uid_b = db.create_user(USER_B["name"], USER_B["email"], USER_B["password"])
        _insert_expenses(uid_b, [(99.00, "Health", "2020-01-10", "b-only-expense")])
        _login(client, USER_B["email"], USER_B["password"])
        page = _text(_get(client, app, **{"from": "2020-01-10", "to": "2020-01-10"}))
        assert "₹99.00" in _total_spent(page)
        assert "b-only-expense" in page and "tx-jan10" not in page


# --------------------------------------------------------------------------
# DB helper contract (keyword-only optional date args)
# --------------------------------------------------------------------------
class TestDbHelpers:
    def test_helpers_without_dates_return_all_rows(self, user_a_id):
        assert len(db.get_recent_expenses(user_a_id)) == 4
        assert db.get_expense_summary(user_a_id) == {"total": 65.0, "count": 4}
        assert sum(r[1] for r in db.get_category_totals(user_a_id)) == pytest.approx(65.0)

    def test_summary_inclusive_bounds(self, user_a_id):
        s = db.get_expense_summary(user_a_id, date_from="2020-01-10", date_to="2020-01-20")
        assert s["count"] == 3 and s["total"] == pytest.approx(60.0)

    def test_summary_one_sided(self, user_a_id):
        assert db.get_expense_summary(user_a_id, date_from="2020-01-20")["count"] == 2
        assert db.get_expense_summary(user_a_id, date_to="2020-01-10")["count"] == 1

    def test_recent_expenses_filtered_and_newest_first(self, user_a_id):
        rows = db.get_recent_expenses(user_a_id, date_from="2020-01-10", date_to="2020-01-20")
        assert [r[0] for r in rows] == ["2020-01-20", "2020-01-15", "2020-01-10"]

    def test_recent_expenses_limit_still_applies_with_filter(self, user_a_id):
        rows = db.get_recent_expenses(user_a_id, 2, date_from="2020-01-01")
        assert len(rows) == 2

    def test_date_args_are_keyword_only(self, user_a_id):
        with pytest.raises(TypeError):
            db.get_expense_summary(user_a_id, "2020-01-10")  # noqa
        with pytest.raises(TypeError):
            db.get_category_totals(user_a_id, "2020-01-10")  # noqa

    def test_helpers_scoped_to_user(self, user_a_id):
        other = db.create_user(USER_B["name"], USER_B["email"], USER_B["password"])
        assert db.get_expense_summary(other, date_from="2020-01-01")["count"] == 0
        assert list(db.get_category_totals(other, date_from="2020-01-01")) == []

    @pytest.mark.parametrize(
        "date_from,date_to",
        [
            (None, None),
            ("2020-01-10", "2020-01-20"),
            ("2020-01-20", None),
            (None, "2020-01-15"),
            ("2020-02-01", "2020-02-01"),
            ("2021-01-01", "2021-12-31"),
        ],
    )
    def test_category_amounts_sum_to_total_spent(self, user_a_id, date_from, date_to):
        total = db.get_expense_summary(user_a_id, date_from=date_from, date_to=date_to)["total"]
        cats = db.get_category_totals(user_a_id, date_from=date_from, date_to=date_to)
        assert sum(r[1] for r in cats) == pytest.approx(total), "Categories must sum to total"
