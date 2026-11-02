import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
AMOUNT = re.compile(r"₹(\d+\.\d{2})")


def login(client, email="demo@spendly.com", password="demo123"):
    return client.post("/login", data={"email": email, "password": password})


def navbar(html):
    return re.search(r'<nav class="navbar">.*?</nav>', html, re.S).group(0)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def profile_html(client):
    login(client)
    res = client.get("/profile")
    assert res.status_code == 200
    return res.data.decode()


# ------------------------------------------------------------------ #
# Access                                                              #
# ------------------------------------------------------------------ #

def test_profile_requires_login(client):
    res = client.get("/profile")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/login")


def test_login_lands_on_rendered_profile(client):
    res = client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert res.request.path == "/profile"
    html = res.data.decode()
    assert 'class="profile"' in html
    assert "coming in Step 4" not in html


def test_title_and_single_h1(client):
    html = profile_html(client)
    assert "<title>Profile — Spendly</title>" in html
    assert html.count("<h1") == 1


# ------------------------------------------------------------------ #
# Content                                                             #
# ------------------------------------------------------------------ #

def test_shows_name_and_avatar_initial(client):
    html = profile_html(client)
    assert re.search(r'class="profile-name">Demo User</h1>', html)
    assert re.search(r'class="profile-avatar"[^>]*>D</div>', html)


def test_shows_email_and_member_since(client):
    html = profile_html(client)
    assert "demo@spendly.com" in html
    assert "Member since" in html


def test_summary_stat_cards(client):
    html = profile_html(client)
    for label in ("Total spent", "Transactions", "Top category"):
        assert f'class="profile-stat-label">{label}</p>' in html
    assert re.search(r'profile-top-category">Bills</p>', html)


def test_transactions_table(client):
    html = profile_html(client)
    for header in ("Date", "Description", "Category"):
        assert f"<th>{header}</th>" in html
    assert '<th class="profile-num">Amount</th>' in html
    assert "profile-pill" in html
    assert re.search(r'<td class="profile-num profile-amount">₹32\.40</td>', html)
    # Every rupee amount has exactly two decimals.
    for match in re.finditer(r"₹([\d.]+)", html):
        assert re.fullmatch(r"\d+\.\d{2}", match.group(1))


def test_category_bars_proportional(client):
    html = profile_html(client)
    rows = re.findall(r'<li class="profile-cat profile-cat--\w+">', html)
    assert len(rows) == 7
    widths = [float(w) for w in re.findall(r'style="width: ([\d.]+)%"', html)]
    amounts = [float(a) for a in re.findall(r'profile-cat-amount">₹([\d.]+)<', html)]
    assert len(widths) == len(amounts) == 7
    assert abs(sum(widths) - 100) <= 0.5
    assert widths.index(max(widths)) == amounts.index(max(amounts))
    assert widths == sorted(widths, reverse=True)
    assert amounts == sorted(amounts, reverse=True)


def test_total_equals_sum_of_categories(client):
    html = profile_html(client)
    amounts = [float(a) for a in re.findall(r'profile-cat-amount">₹([\d.]+)<', html)]
    total = float(re.search(r'profile-total-spent">₹([\d.]+)<', html).group(1))
    assert round(sum(amounts), 2) == total == 222.19


def test_add_expense_link(client):
    html = profile_html(client)
    assert 'href="/expenses/add"' in html
    assert "url_for('add_expense')" in read("templates", "profile.html")


def test_empty_transactions_state(app):
    from flask import render_template

    with app.test_request_context():
        html = render_template(
            "profile.html",
            user={"name": "A", "initial": "A", "email": "a@b.co", "member_since": "Today"},
            stats={"total_spent": 0, "transaction_count": 0, "top_category": "—"},
            transactions=[],
            categories=[],
        )
    assert "No transactions yet." in html
    assert "<table" not in html


def test_user_name_is_escaped(client):
    name = "<script>alert(1)</script>"
    client.post(
        "/register",
        data={"name": name, "email": "xss@example.com", "password": "password123"},
    )
    login(client, "xss@example.com", "password123")
    html = client.get("/profile").data.decode()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)" not in html
    assert "|safe" not in read("templates", "profile.html")


# ------------------------------------------------------------------ #
# Navbar                                                              #
# ------------------------------------------------------------------ #

def test_navbar_name_links_to_profile(client):
    login(client)
    nav = navbar(client.get("/").data.decode())
    assert '<a href="/profile" class="nav-user">Demo User</a>' in nav


def test_nav_user_visible_on_mobile():
    css = read("static", "css", "style.css")
    assert ".nav-links a:not(.nav-cta):not(.nav-user)" in css
    assert ".nav-links a:not(.nav-cta) {" not in css


def test_logout_from_profile(client):
    login(client)
    res = client.get("/logout")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/")
    assert client.get("/profile").headers["Location"].endswith("/login")


# ------------------------------------------------------------------ #
# Styles and scripts                                                  #
# ------------------------------------------------------------------ #

def test_profile_css_linked_and_tokens_only(client):
    html = profile_html(client)
    assert "css/profile.css" in html
    css = read("static", "css", "profile.css")
    template = read("templates", "profile.html")
    assert not HEX.search(css)
    assert not HEX.search(template)
    assert "<style" not in template
    styles = re.findall(r'style="([^"]*)"', template)
    assert styles == ["width: {{ c.pct }}%"]


def test_lucide_loaded_pinned_and_initialised():
    base = read("templates", "base.html")
    js = read("static", "js", "main.js")
    assert "lucide@latest" not in base
    lucide_pos = base.find("unpkg.com/lucide@0.")
    assert lucide_pos != -1
    assert lucide_pos < base.find("js/main.js")
    assert "if (window.lucide)" in js
    assert "lucide.createIcons()" in js


# ------------------------------------------------------------------ #
# Step 5 — real DB data                                               #
# ------------------------------------------------------------------ #

def register_and_login(client, email="new@example.com", name="New User"):
    client.post(
        "/register",
        data={"name": name, "email": email, "password": "password123"},
    )
    login(client, email, "password123")


def test_missing_user_clears_session_and_redirects(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 9999
        sess["user_name"] = "Ghost"
    res = client.get("/profile")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_user_card_from_db(client):
    html = profile_html(client)
    assert "demo@spendly.com" in html
    assert re.search(r"Member since [A-Z][a-z]+ \d{4}", html)


def test_profile_data_isolated_between_users(client):
    register_and_login(client)
    res = client.get("/profile")
    assert res.status_code == 200
    html = res.data.decode()
    assert "new@example.com" in html
    assert "demo@spendly.com" not in html
    assert "Groceries" not in html
    assert 'profile-total-spent">₹0.00<' in html


TX_AMOUNT = re.compile(r'<td class="profile-num profile-amount">₹([\d.]+)</td>')


def test_transactions_from_db_newest_first(client):
    html = profile_html(client)
    amounts = TX_AMOUNT.findall(html)
    assert len(amounts) == 8
    assert amounts == [
        "32.40", "7.25", "45.30", "15.99", "20.00", "85.00", "3.75", "12.50",
    ]


def test_transaction_date_formatted_from_db(client):
    from datetime import date

    html = profile_html(client)
    first_row = re.search(r"<tbody>.*?</tr>", html, re.S).group(0)
    assert date.today().strftime("%d %b %Y") in first_row


def test_new_user_sees_no_transactions(client):
    register_and_login(client)
    html = client.get("/profile").data.decode()
    assert "No transactions yet." in html
    assert not TX_AMOUNT.search(html)


def test_format_date_unit(app):
    import importlib

    format_date = importlib.import_module("app")._format_date
    assert format_date("2026-01-05") == "05 Jan 2026"


def test_stats_for_demo_user(client):
    html = profile_html(client)
    assert 'profile-total-spent">₹222.19<' in html
    assert re.search(
        r'profile-stat-label">Transactions</p>\s*<p class="profile-stat-value">8</p>',
        html,
    )
    assert 'profile-top-category">Bills<' in html


def test_stats_for_new_user_are_zero(client):
    register_and_login(client, email="stats@example.com", name="Stats User")
    res = client.get("/profile")
    assert res.status_code == 200
    html = res.data.decode()
    assert 'profile-total-spent">₹0.00<' in html
    assert re.search(
        r'profile-stat-label">Transactions</p>\s*<p class="profile-stat-value">0</p>',
        html,
    )
    assert 'profile-top-category">—<' in html


def test_categories_from_db_ordered_and_aggregated(client):
    html = profile_html(client)
    names = re.findall(r'<li class="profile-cat profile-cat--(\w+)">', html)
    assert len(names) == 7
    assert names[:3] == ["bills", "shopping", "food"]
    assert 'profile-cat-amount">₹44.90<' in html


def test_categories_empty_state_for_new_user(client):
    register_and_login(client)
    html = client.get("/profile").data.decode()
    assert "No spending yet." in html
    assert "profile-cat-total" not in html


def test_category_pcts_empty_and_zero_total(app):
    import importlib

    category_pcts = importlib.import_module("app")._category_pcts
    assert category_pcts([]) == []
    assert category_pcts([("Food", 0.0)]) == []


# ------------------------------------------------------------------ #
# Step 6 — date filter                                                #
# ------------------------------------------------------------------ #

import html as html_lib  # noqa: E402
import importlib  # noqa: E402
from datetime import date  # noqa: E402

import pytest  # noqa: E402

from database import db  # noqa: E402

# Year 2020 never overlaps the current-month demo seed.
EDGE_ROWS = [
    (1.00, "Food", "2020-01-14", "BeforeEdge"),
    (10.00, "Food", "2020-01-15", "StartEdge"),
    (5.50, "Transport", "2020-01-20", "MiddleRow"),
    (20.25, "Bills", "2020-01-31", "EndEdge"),
    (100.00, "Health", "2020-02-01", "AfterEdge"),
]
JAN = {"from": "2020-01-15", "to": "2020-01-31"}
TX_COUNT = re.compile(
    r'profile-stat-label">Transactions</p>\s*<p class="profile-stat-value">(\d+)</p>'
)


def app_module():
    return importlib.import_module("app")


def add_expenses(email, rows):
    """rows: (amount, category, iso_date, description). Returns user_id."""
    conn = db.get_db()
    try:
        uid = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()["id"]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [(uid, *row) for row in rows],
        )
        conn.commit()
        return uid
    finally:
        conn.close()


def filtered_html(client, **params):
    login(client)
    add_expenses("demo@spendly.com", EDGE_ROWS)
    res = client.get("/profile", query_string=params)
    assert res.status_code == 200
    return res.data.decode()


def total(page):
    return re.search(r'profile-total-spent">₹([\d.]+)<', page).group(1)


def tx_count(page):
    return int(TX_COUNT.search(page).group(1))


def presets_by_label(today):
    return {
        p["label"]: (p["from"], p["to"])
        for p in app_module()._date_presets(today)
    }


# --- unit ------------------------------------------------------------ #

def test_parse_date_filter_unit(app):
    m = app_module()
    parse = m._parse_date_filter
    none = {"date_from": None, "date_to": None, "error": None}
    assert parse({}) == none
    assert parse({"from": "", "to": ""}) == none
    assert parse({"from": "2020-01-15"}) == {
        "date_from": "2020-01-15", "date_to": None, "error": None}
    assert parse({"to": "2020-01-15"}) == {
        "date_from": None, "date_to": "2020-01-15", "error": None}
    assert parse({"from": "2020-01-15", "to": "2020-01-15"})["error"] is None
    assert parse({"from": " 2020-01-15 "})["date_from"] == "2020-01-15"
    assert parse({"from": "2020-1-5"})["date_from"] == "2020-01-05"
    invalid = {"date_from": None, "date_to": None, "error": m.INVALID_DATE_ERROR}
    assert parse({"from": "bad"}) == invalid
    assert parse({"to": "2020-02-30"}) == invalid
    assert parse({"from": "2020-01-15", "to": "nope"}) == invalid
    assert parse({"from": "2020-01-31", "to": "2020-01-15"}) == {
        "date_from": None, "date_to": None, "error": m.DATE_ORDER_ERROR}


def test_date_presets_jan_rolls_back_year(app):
    presets = app_module()._date_presets(date(2026, 1, 20))
    assert [p["label"] for p in presets] == [
        "All time", "This month", "Last month", "Last 3 months"]
    by = presets_by_label(date(2026, 1, 20))
    assert by["All time"] == (None, None)
    assert by["This month"] == ("2026-01-01", "2026-01-20")
    assert by["Last month"] == ("2025-12-01", "2025-12-31")
    assert by["Last 3 months"] == ("2025-11-01", "2026-01-20")


def test_date_presets_month_end_and_leap(app):
    by = presets_by_label(date(2026, 3, 31))
    assert by["Last month"] == ("2026-02-01", "2026-02-28")
    assert by["Last 3 months"][0] == "2026-01-01"
    assert presets_by_label(date(2024, 3, 15))["Last month"][1] == "2024-02-29"
    assert presets_by_label(date(2026, 2, 1))["Last 3 months"][0] == "2025-12-01"


def test_build_filter_active_preset_and_params(app):
    m = app_module()
    today = date(2026, 1, 20)

    f = m._build_filter({"date_from": None, "date_to": None, "error": None}, today)
    assert f["active"] is False
    assert f["active_preset"] == "All time"
    assert f["presets"][0]["params"] == {}
    assert f["presets"][1]["params"] == {"from": "2026-01-01", "to": "2026-01-20"}

    f = m._build_filter(
        {"date_from": "2026-01-01", "date_to": "2026-01-20", "error": None}, today)
    assert f["active"] is True
    assert f["active_preset"] == "This month"

    f = m._build_filter(
        {"date_from": "2026-01-05", "date_to": None, "error": None}, today)
    assert f["active"] is True
    assert f["active_preset"] is None


def test_db_helpers_default_unchanged_and_keyword_only(app):
    assert db.get_expense_summary(1) == db.get_expense_summary(
        1, date_from=None, date_to=None)
    summary = db.get_expense_summary(1)
    assert summary["count"] == 8
    assert summary["total"] == pytest.approx(222.19)
    with pytest.raises(TypeError):
        db.get_recent_expenses(1, 10, "2020-01-01")


# --- integration ----------------------------------------------------- #

def test_filter_bar_markup(client):
    page = profile_html(client)
    assert 'aria-label="Date filter"' in page
    for label in ("All time", "This month", "Last month", "Last 3 months"):
        assert f">{label}</a>" in page
    assert re.search(r'type="date"[^>]*name="from"', page)
    assert re.search(r'type="date"[^>]*name="to"', page)
    assert ">Apply</button>" in page
    assert 'method="get" action="/profile"' in page
    assert "profile-filter-clear" not in page
    assert 'role="alert"' not in page


def test_no_params_all_time_active(client):
    page = profile_html(client)
    assert total(page) == "222.19"
    assert tx_count(page) == 8
    assert "Showing all time" in page
    assert re.search(
        r'profile-filter-preset--active" aria-current="true">All time</a>', page)
    assert page.count('aria-current="true"') == 1


def test_inclusive_bounds(client):
    page = filtered_html(client, **JAN)
    assert total(page) == "35.75"
    assert tx_count(page) == 3
    for desc in ("StartEdge", "MiddleRow", "EndEdge"):
        assert desc in page
    for desc in ("BeforeEdge", "AfterEdge", "Groceries"):
        assert desc not in page


def test_only_from(client):
    page = filtered_html(client, **{"from": "2020-01-31"})
    assert total(page) == "342.44"
    assert tx_count(page) == 10


def test_only_to(client):
    page = filtered_html(client, to="2020-01-15")
    assert total(page) == "11.00"
    assert tx_count(page) == 2


def test_empty_range(client):
    page = filtered_html(client, **{"from": "2019-01-01", "to": "2019-12-31"})
    assert total(page) == "0.00"
    assert tx_count(page) == 0
    assert 'profile-top-category">—<' in page
    assert "No transactions in this period." in page
    assert "No spending in this period." in page
    assert "No transactions yet." not in page
    assert "No spending yet." not in page


def test_invalid_date_shows_error_all_time(client):
    m = app_module()
    page = filtered_html(client, **{"from": "not-a-date"})
    assert f'role="alert">{m.INVALID_DATE_ERROR}</p>' in page
    assert total(page) == "358.94"  # all time: 222.19 seed + 136.75 edge rows
    assert re.search(r'preset--active" aria-current="true">All time</a>', page)


def test_reversed_range_error(client):
    m = app_module()
    login(client)
    res = client.get(
        "/profile", query_string={"from": "2026-10-31", "to": "2026-10-01"})
    assert res.status_code == 200
    page = res.data.decode()
    assert m.DATE_ORDER_ERROR in page
    assert total(page) == "222.19"


def test_empty_strings_are_missing(client):
    login(client)
    page = client.get("/profile?from=&to=").data.decode()
    assert 'role="alert"' not in page
    assert total(page) == "222.19"


def test_inputs_prefilled_and_clear_link(client):
    page = filtered_html(client, **JAN)
    assert 'value="2020-01-15"' in page
    assert 'value="2020-01-31"' in page
    assert '<a href="/profile" class="btn-ghost profile-filter-clear">' in page


def test_caption(client):
    page = filtered_html(client, **JAN)
    assert "Showing 15 Jan 2020 – 31 Jan 2020" in page
    page = client.get("/profile", query_string={"from": "2020-01-15"}).data.decode()
    assert "Showing from 15 Jan 2020" in page
    page = client.get("/profile", query_string={"to": "2020-01-31"}).data.decode()
    assert "Showing up to 31 Jan 2020" in page


def test_this_month_preset_link_and_filter(client):
    page = filtered_html(client)
    match = re.search(
        r'<a href="([^"]+)" class="profile-filter-preset[^"]*"[^>]*>This month</a>',
        page,
    )
    href = html_lib.unescape(match.group(1))
    today = date.today()
    assert f"from={today.replace(day=1).isoformat()}" in href
    assert f"to={today.isoformat()}" in href
    page = client.get(href).data.decode()
    assert re.search(r'preset--active" aria-current="true">This month</a>', page)
    assert total(page) == "222.19"
    assert "StartEdge" not in page


def test_custom_range_no_active_preset(client):
    page = filtered_html(client, **JAN)
    assert "profile-filter-preset--active" not in page
    assert 'aria-current="true"' not in page


def test_filtered_categories_sum_to_total(client):
    page = filtered_html(client, **JAN)
    amounts = re.findall(r'profile-cat-amount">₹([\d.]+)<', page)
    assert round(sum(float(a) for a in amounts), 2) == 35.75
    pcts = re.findall(r'profile-cat-pct">([\d.]+)%<', page)
    assert abs(sum(float(p) for p in pcts) - 100) < 0.5


def test_filter_isolated_between_users(client):
    register_and_login(client, email="other@example.com", name="Other")
    add_expenses(
        "other@example.com", [(999.0, "Food", "2020-01-20", "OtherUserSecret")])
    client.get("/logout")
    page = filtered_html(client, **JAN)
    assert "OtherUserSecret" not in page
    assert total(page) == "35.75"
    page = client.get(
        "/profile", query_string={**JAN, "user_id": "2"}).data.decode()
    assert "OtherUserSecret" not in page
    assert total(page) == "35.75"


def test_logged_out_filter_redirects(client):
    res = client.get("/profile?from=2020-01-01")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/login")


def test_filter_query_values_escaped(client):
    m = app_module()
    login(client)
    res = client.get(
        "/profile", query_string={"from": '"><script>alert(1)</script>'})
    assert res.status_code == 200
    page = res.data.decode()
    assert "<script>alert(1)" not in page
    assert m.INVALID_DATE_ERROR in page


def test_filter_template_rules():
    tpl = read("templates", "profile.html")
    assert tpl.count("url_for('profile'") >= 3
    assert "/profile?" not in tpl
    assert "|safe" not in tpl
    css = read("static", "css", "profile.css")
    for selector in (
        ".profile-filter {",
        ".profile-filter-preset--active",
        ".profile-filter-error",
        ".profile-filter-caption",
    ):
        assert selector in css
    mobile = css[css.index("@media (max-width: 600px)"):]
    assert ".profile-filter-form" in mobile
