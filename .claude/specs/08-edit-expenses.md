# Spec: Edit Expenses

## Overview
Through Step 7, users can add expenses, but a mistake (wrong amount, wrong
category, a typo in the description) can only be fixed by hand in the
database. `/expenses/<id>/edit` is still a stub that returns a plain string,
and nothing on `/profile` links to it. This step turns it into a working
feature. Each row in the profile's recent-transactions table gets an "Edit"
link. That link opens a form pre-filled with the expense's current values,
which uses the same fields and validation as the add form. On a valid submit
the row is updated and the user is redirected to `/profile`. A user can only
see and edit their **own** expenses. Any other id, or an id that doesn't
exist, returns 404. This is the first step where a URL carries a record id,
so the ownership check is the core of the feature. Delete (Step 9) will reuse
the same ownership lookup.

## Depends on
- **Step 1 — Database setup** (complete): the `expenses` table, `CATEGORIES`,
  and `get_db()` with `PRAGMA foreign_keys = ON`.
- **Step 3 — Login and Logout** (complete): `session["user_id"]`.
- **Step 5 — Backend Routes for Profile Page** (complete): `/profile`,
  `_build_transactions()` and `get_recent_expenses()`, which this step extends
  with the expense `id`.
- **Step 7 — Add New Expenses** (complete): `_parse_expense_form()`,
  `_expense_form_values()`, `_session_user()`, the error constants, the
  `add_expense.html` form layout, and `static/css/expense.css`. All of them
  are reused here.

## Routes
- `GET /expenses/<int:id>/edit` — renders the edit form pre-filled with the
  expense's current amount (formatted to 2 dp), category, date and
  description (`''` when `NULL`). — logged-in, owner only
- `POST /expenses/<int:id>/edit` — validates with `_parse_expense_form()`. If
  it is valid, updates the expense and returns a `302` redirect to
  `url_for('profile')`. If it is invalid, re-renders the form with HTTP `400`,
  one error message, and the submitted values kept. — logged-in, owner only

Both methods live on the **existing** `edit_expense` endpoint. Keep the
function name `edit_expense` and change the decorator to
`methods=["GET", "POST"]`. Rename the path parameter from `id` to
`expense_id` (`/expenses/<int:expense_id>/edit`) so it doesn't shadow the
builtin, and update the function signature to match.

### Access rules
Apply these in order on **both** GET and POST:
1. No `session["user_id"]` → `302` to `url_for('login')`. Nothing is read or
   written.
2. Stale session (user deleted) → `_session_user()` clears it → `302` to
   `login`, the same as `/profile` and `/expenses/add`.
3. Look up the expense with
   `get_expense_by_id(expense_id, user_id)`, scoped to the session user. If
   the result is `None`, call `abort(404)`. That covers both "doesn't exist"
   and "belongs to someone else", so the response never reveals whether
   another user's expense id exists. Never return 403 here.
4. `user_id` **always** comes from the session. Ignore any `user_id` or `id`
   field in the form body.

A non-integer id (`/expenses/abc/edit`) already returns 404 through Flask's
`int` converter, so no extra code is needed.

### Validation (POST)
Reuse `_parse_expense_form(request.form, date.today())` from Step 7
unchanged: same field order, same rules, same error constants, first error
wins. Do **not** copy or fork the validation. A date in the future is still
rejected, and an expense dated in the past keeps passing.

### CSRF token (edit form only)
The comment on `app.config` in `app.py` says a per-form CSRF token was planned
before the edit and delete steps. Implement a minimal, standard-library-only
token for this form:
- Add a helper `_csrf_token()` that creates
  `session["csrf_token"] = secrets.token_urlsafe(32)` the first time it's
  called and returns it.
- `GET` passes `csrf_token=_csrf_token()` to the template. The form renders it
  as `<input type="hidden" name="csrf_token" value="...">`.
- `POST` compares `request.form.get("csrf_token", "")` with the session value
  using `hmac.compare_digest`. A missing or mismatched token → `abort(400)`,
  checked **after** the login and ownership checks and **before**
  validation. Nothing is updated.
- `session.clear()` on login and logout already rotates the token. No extra
  work is needed.
- **Do not** add the token to the add form in this step: that would change
  Step 7 behaviour and its tests. Retrofitting it is a separate follow-up.

## Database changes
No schema changes. Verified against `database/db.py`: `expenses` already has
`id`, `user_id` (FK → `users.id`), `amount`, `category`, `date`,
`description` (nullable) and `created_at`. No new tables, columns or indexes.

**New helpers** in `database/db.py`:

```python
def get_expense_by_id(expense_id, user_id):
    """Return the expense row (id, amount, category, date, description) if it
    belongs to ``user_id``, else None."""

def update_expense(expense_id, user_id, amount, category, date, description=None):
    """Update one expense owned by ``user_id``. Return True if a row changed."""
```

- `get_expense_by_id`: `SELECT id, amount, category, date, description FROM
  expenses WHERE id = ? AND user_id = ?`. The ownership filter belongs in the
  SQL, not in Python afterwards.
- `update_expense`: `UPDATE expenses SET amount = ?, category = ?, date = ?,
  description = ? WHERE id = ? AND user_id = ?`, then commit and return
  `cur.rowcount == 1`. Never update `user_id` or `created_at`.
- Both use `get_db()`, close in `finally`, and use static `?`-parameterised
  SQL, the same as `create_expense`.
- If `update_expense` returns `False` (the row was deleted between GET and
  POST), the route calls `abort(404)`.

**Modified helper:** `get_recent_expenses()` also selects `id`. The column
list becomes `id, date, description, category, amount`, so the profile table
can link to each row. Existing callers that read the other columns by name
are unaffected.

## Templates
- **Create:**
  - `templates/edit_expense.html`: extends `base.html`, with title
    "Edit expense — Spendly". It loads `css/expense.css` in
    `{% block head %}`. It uses the same structure and classes as
    `add_expense.html`:
    1. A heading "Edit expense" and a short subtitle.
    2. The `expense-error` banner (`role="alert"`) when `error` is set.
    3. `<form method="POST" action="{{ url_for('edit_expense',
       expense_id=expense_id) }}">` with the same four fields, attributes and
       labels as the add form, plus the hidden `csrf_token` input.
    4. Values come from `form_values`: the DB row on GET, and the submitted
       values after a failed POST.
    5. Actions: a "Cancel" link to `url_for('profile')` and a submit button
       "Save changes".
    6. Autoescaping only, never `|safe`.
- **Modify:**
  - `templates/profile.html`: add a final narrow column to the
    recent-transactions table (header visually labelled or `<span
    class="sr-only">Actions</span>`). Each row gets
    `<a href="{{ url_for('edit_expense', expense_id=t.id) }}"
    class="profile-edit-link" aria-label="Edit {{ t.description or t.category }}
    on {{ t.date }}">Edit</a>`. A Lucide `pencil` icon is optional.

## Files to change
- `app.py`:
  - Import `abort` from flask, `hmac` and `secrets` from the standard library,
    and `get_expense_by_id` and `update_expense` from `database.db`.
  - `_build_transactions()`: include `"id": row["id"]` in each dict.
  - Add a pure helper `_expense_row_values(row)` that turns a DB row into
    `form_values` (amount as `f"{row['amount']:.2f}"`, description `""` when
    `NULL`).
  - Add `_csrf_token()` and a small `_render_edit_expense(expense_id,
    form_values, today, error=None)` helper that mirrors
    `_render_add_expense`.
  - Replace the `edit_expense` stub with the GET/POST handler described above.
    Keep it thin, with no SQL in it.
  - Leave the `delete_expense` stub untouched.
- `database/db.py`: add `get_expense_by_id()` and `update_expense()`, and add
  `id` to the `get_recent_expenses()` SELECT.
- `templates/profile.html`: the edit link column described above.
- `static/css/profile.css`: `.profile-edit-link` (and the actions column
  width) using only `:root` tokens.
- `CLAUDE.local.md`: change the routes-table row to
  `GET/POST /expenses/<id>/edit` | Implemented — Step 8 (login required,
  owner only).
- `README.md`: update the `/expenses/<id>/edit` row to `GET/POST` |
  Implemented.

## Files to create
- `.claude/specs/08-edit-expenses.md` (this spec)
- `templates/edit_expense.html`
- `tests/test_08-edit-expenses.py`: pytest tests that use the existing
  `app`/`client` fixtures in `tests/conftest.py`.

## New dependencies
No new dependencies. Use Flask plus the standard library only (`secrets`,
`hmac`, `datetime`, `math`).

## Rules for implementation
- No SQLAlchemy or ORMs. Use raw `sqlite3` through `get_db()` only.
- Parameterised queries only (`?` placeholders). Never use f-strings, `%` or
  `.format()` to build SQL.
- Passwords hashed with werkzeug. This step touches no passwords.
- Use CSS variables and never hardcode hex values. No inline `<style>` tags or
  `style=""` attributes.
- All templates extend `base.html`.
- All SQL lives in `database/db.py`. `app.py` only checks access, validates,
  calls helpers, and renders or redirects.
- **The ownership check is done in SQL** (`WHERE id = ? AND user_id = ?`) for
  both the read and the update. Never fetch by id alone and compare in
  Python, and never trust an id or user_id from the form.
- Another user's expense, a missing expense, and a deleted-mid-edit expense
  all return **404**, through `abort(404)`, never a string return.
- Reuse `_parse_expense_form()` unchanged. Do not duplicate the validation
  rules or the `CATEGORIES` list.
- Use `url_for()` for every link, the form `action`, and the redirect. Never
  hardcode `/expenses/...` or `/profile`.
- Use Post/Redirect/Get: a successful POST always redirects.
- Bad form input never causes a 500. It returns `400` with the form
  re-rendered. A bad or missing CSRF token returns a plain `abort(400)`.
- No JavaScript is required. The form must work with JS disabled.
- Do not implement delete (Step 9). Do not change add-expense behaviour.
- Keep the app on port 5001.

## Definition of done
- [ ] Logged out, `GET` and `POST /expenses/1/edit` both redirect to `/login`, and the expense is unchanged
- [ ] Logged in as the demo user, every row in "Recent transactions" on `/profile` has an "Edit" link to `/expenses/<that row's id>/edit`
- [ ] Clicking "Edit" on "Lunch" opens a form pre-filled with amount `12.50`, category Food, the expense's date, and description "Lunch"
- [ ] Changing the amount to `20` and submitting redirects to `/profile`, where the Lunch row shows ₹20.00, the total rises by ₹7.50, and the transaction count is unchanged
- [ ] Changing the category updates the category breakdown on `/profile` accordingly
- [ ] Clearing the description stores `NULL`, and the row still appears on `/profile`
- [ ] The edited row keeps its original `id`, `user_id` and `created_at`, and no new row is inserted
- [ ] Invalid input (amount `0`/`abc`/`1000001`, category `Crypto`, date `2026-13-45` or tomorrow, description over 200 chars) → HTTP 400 with the same error messages as the add form, the submitted values kept, and the DB row unchanged
- [ ] User B requesting `GET` or `POST /expenses/<user A's expense id>/edit` gets 404, and user A's expense is unchanged
- [ ] `GET /expenses/999999/edit` → 404; `GET /expenses/abc/edit` → 404
- [ ] A forged `user_id` field in the POST body does not move the expense to another user
- [ ] A POST with a missing or wrong `csrf_token` → 400, and the expense is unchanged
- [ ] A stale session (user deleted) on the edit route clears the session and redirects to `/login`
- [ ] Changing an expense's date from this month to last month moves it from the "This month" preset to the "Last month" preset on `/profile`
- [ ] No SQL strings in `app.py`. `get_expense_by_id` and `update_expense` use static `?`-parameterised SQL with `user_id` in the `WHERE` clause
- [ ] The edit page reuses `expense.css`, uses only CSS variables, and stacks cleanly at ~375px wide. The profile table's edit column doesn't break the mobile layout
- [ ] The add-expense form and its tests behave exactly as before, and the delete route is still a stub
- [ ] App runs on port 5001, and `pytest` passes, including `tests/test_08-edit-expenses.py` and every existing test unchanged
