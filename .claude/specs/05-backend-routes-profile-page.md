# Spec: Backend Routes for Profile Page

## Overview
Step 4 built the profile page layout, but almost all of its data is hardcoded
placeholder data in `app.py` (`PLACEHOLDER_EMAIL`, `PLACEHOLDER_MEMBER_SINCE`,
`PLACEHOLDER_TRANSACTION_COUNT`, `PLACEHOLDER_TRANSACTIONS`,
`PLACEHOLDER_CATEGORY_AMOUNTS`). Only the user's name comes from the session.
This step connects `/profile` to the SQLite database. The route loads the
logged-in user's row and their expenses through new query helpers in
`database/db.py`. The user card, summary stats, recent transactions and
category breakdown then show real data for the user in `session["user_id"]`.
The visual design from Step 4 stays the same. The template changes only to
handle users who have no expenses yet. After this step the profile page is a
real dashboard, ready for the add, edit and delete steps (7–9).

## Depends on
- **Step 1 — Database setup** (complete): `users` and `expenses` tables,
  `get_db()` with `PRAGMA foreign_keys = ON`, and `seed_db()` demo data.
- **Step 2 — Registration** (complete): new users exist with `created_at`
  set and no expenses, which is the empty-state case.
- **Step 3 — Login and Logout** (complete): sets `session["user_id"]` and
  `session["user_name"]`.
- **Step 4 — Profile Page Design** (complete): `templates/profile.html`,
  `static/css/profile.css`, and the context shape (`user`, `stats`,
  `transactions`, `categories`).

## Routes
- `GET /profile` — existing route, now backed by the database: load the user
  by `session["user_id"]` and render their real profile data. If no one is
  logged in, redirect to `login`. If the session's user id no longer exists in
  the DB, clear the session and redirect to `login` — logged-in

No new routes.

## Database changes
No database changes. Verified against `database/db.py`: `users` has `id`,
`name`, `email` and `created_at`, and `expenses` has `user_id`, `amount`,
`category`, `date` and `description`. Every value the page shows can be
computed from these columns. No new tables, columns or indexes.

New **query helpers** in `database/db.py` (functions, not schema changes):
- `get_user_by_id(user_id)` returns the `users` row as `sqlite3.Row`, or `None`.
- `get_expense_summary(user_id)` returns a dict with `total` (float, `0.0`
  when there are no expenses) and `count` (int), from one
  `SELECT COALESCE(SUM(amount), 0), COUNT(*)` query.
- `get_recent_expenses(user_id, limit=10)` returns a list of rows (`date`,
  `description`, `category`, `amount`) ordered by `date DESC, id DESC`.
- `get_category_totals(user_id)` returns a list of `(category, amount)` rows
  from a `GROUP BY category` query, ordered by `amount DESC, category ASC` so
  ties come back in a stable order.

Every helper opens a connection with `get_db()`, uses `?` placeholders, filters
by `user_id`, and closes the connection in a `finally` block. This follows the
existing `get_user_by_email` pattern.

## Templates
- **Create:** none
- **Modify:**
  - `templates/profile.html`:
    - **Spending by category:** add an `{% else %}` empty state (for example
      "No spending yet.") when `categories` is empty, and hide the total line
      in that case.
    - **Top category:** when it is `None`, show a placeholder such as `—`.
    - No other markup or class changes. Existing test hooks such as
      `profile-name`, `profile-total-spent` and `profile-top-category` must
      keep working.

## Files to change
- `app.py`:
  - Delete all `PLACEHOLDER_*` constants and the "Step 4 placeholder" comment.
  - Import the new helpers from `database.db`.
  - Rewrite `profile()`:
    1. If `session.get("user_id")` is missing, redirect to login.
    2. Call `get_user_by_id`. If it returns `None`, run `session.clear()` and
       redirect to login.
    3. Call the three expense helpers.
    4. Build `user`, `stats`, `transactions` and `categories` with the same
       keys as Step 4.
    5. Render the template.
  - Add small pure presentation helpers next to `_registration_error`, with
    no SQL:
    - `_format_date(iso)`: `YYYY-MM-DD` → `DD Mon YYYY`.
    - `_format_month(created_at)`: `YYYY-MM-DD HH:MM:SS` → `Month YYYY`.
    - Category percentage computation that returns `0` per category when
      the total is `0`, so it never divides by zero.
  - Take the user's name and email from the DB row, not from the session.
- `database/db.py`: add the four query helpers listed above.
- `templates/profile.html`: empty states, as described above.
- `tests/test_profile.py`: replace placeholder-based assertions with ones
  based on the DB data. Cover the demo user's seeded data, a freshly
  registered user with zero expenses, and isolation between users.
- `CLAUDE.local.md`: update the `GET /profile` row in the routes table to
  "Implemented — Step 5 (real DB data, login required)".

## Files to create
- `.claude/specs/05-backend-routes-profile-page.md` (this spec)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs. Use raw `sqlite3` through `get_db()` only.
- Parameterised queries only (`?` placeholders). Never use f-strings or
  `%` formatting in SQL.
- Passwords hashed with werkzeug. This step reads no passwords and must never
  pass `password_hash` to the template.
- Use CSS variables and never hardcode hex values. Any new CSS for empty states
  goes in `profile.css` and uses the existing `:root` tokens.
- All templates extend `base.html`.
- All SQL lives in `database/db.py`. The route only calls helpers, shapes the
  context and renders.
- Every query is scoped by `user_id` from the session. A user must never see
  another user's data. `user_id` never comes from the URL or request args.
- Do the aggregation in SQL (`SUM`, `COUNT`, `GROUP BY`), not by loading every
  expense into Python.
- Close every connection in `finally`.
- Category percentages are rounded to 1 decimal and add up to about 100.
  When the total is 0, return empty data and never divide by zero.
- Currency stays `₹` with two decimals, using the existing
  `"%.2f"|format(...)` in the template.
- Rely on Jinja autoescaping. Never use `|safe` on user-supplied text.
- Use `url_for()` for every redirect and link.
- Keep the inline session check in this route. Do not add a
  `login_required` decorator in this step.
- Do not implement `/expenses/add`, edit or delete. They stay stubs.
- Keep the app on port 5001.

## Definition of done
- [ ] Visiting `/profile` while logged out redirects to `/login`
- [ ] Logging in as `demo@spendly.com` / `demo123` renders `/profile` with HTTP 200
- [ ] The user card shows the name and email from the `users` row, and a "Member since" month and year taken from `created_at`
- [ ] "Total spent" equals the sum of the demo user's seeded expenses (₹222.19)
- [ ] "Transactions" shows the real expense count for the user (8 for the demo user)
- [ ] "Top category" is the category with the highest total (Bills for the demo user)
- [ ] The recent-transactions table lists the user's expenses, newest date first, with dates shown as `DD Mon YYYY`
- [ ] The spending-by-category section lists only the categories the user has spent in, ordered by amount, and the bar widths match the percentages
- [ ] The category amounts add up to the "Total spent" value
- [ ] A newly registered user with no expenses sees ₹0.00, 0 transactions, a `—` top category, and empty-state messages, with no error or 500
- [ ] One user's profile never shows another user's expenses (covered by a test with two users)
- [ ] If the session's `user_id` points to a deleted or missing user, `/profile` clears the session and redirects to `/login`
- [ ] No `PLACEHOLDER_` constants remain in `app.py`
- [ ] No SQL strings appear in `app.py`, and every new query in `db.py` uses `?` placeholders
- [ ] App runs on port 5001, and `pytest` passes, including the updated `tests/test_profile.py`
