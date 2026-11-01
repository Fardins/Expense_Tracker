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
