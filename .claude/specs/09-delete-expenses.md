# Spec: Delete Expenses

## Overview
Through Step 8, users can add and edit expenses, but an expense entered by
mistake (a duplicate, a test entry, a cancelled purchase) can't be removed.
`/expenses/<id>/delete` is still a stub that returns a plain string, and
nothing on `/profile` links to it. This step turns it into a working feature.
Each row in the profile's recent-transactions table gets a "Delete" link next
to "Edit". The link opens a confirmation page that shows the expense's
details. Submitting that page's form (a `POST` with a CSRF token) permanently
deletes the row and redirects to `/profile`. A user can only see and delete
their **own** expenses. Any other id, or an id that doesn't exist, returns 404.
This step reuses the ownership lookup (`get_expense_by_id`) and the CSRF
helpers (`_csrf_token`, `_csrf_valid`) from Step 8. A `GET` request never
deletes anything. Deletion only happens on a validated `POST`, so a link,
prefetch or crawler can't delete data.

## Depends on
- **Step 1 — Database setup** (complete): the `expenses` table and `get_db()`
  with `PRAGMA foreign_keys = ON`.
- **Step 3 — Login and Logout** (complete): `session["user_id"]`.
  `session.clear()` on login and logout rotates the CSRF token.
- **Step 5 — Backend Routes for Profile Page** (complete): `/profile` and
  `_build_transactions()`, whose dicts already include `id`.
- **Step 7 — Add New Expenses** (complete): `_session_user()`,
  `static/css/expense.css`, and the `expense-*` page layout classes.
- **Step 8 — Edit Expenses** (complete): `get_expense_by_id(expense_id,
  user_id)`, `_csrf_token()`, `_csrf_valid()`, `_format_date()`, and the
  profile table's actions column (`.profile-edit-col`, `.profile-edit-link`).

## Routes
- `GET /expenses/<int:expense_id>/delete` — renders a confirmation page with
  the expense's date, description (or category when it is empty), category and
  amount, and a `POST` form with the CSRF token. Deletes nothing. — logged-in,
  owner only
- `POST /expenses/<int:expense_id>/delete` — validates the CSRF token,
  deletes the expense, and returns a `302` redirect to `url_for('profile')`. —
  logged-in, owner only

Both methods live on the **existing** `delete_expense` endpoint. Keep the
function name `delete_expense` and change the decorator to
`methods=["GET", "POST"]`. Rename the path parameter from `id` to
`expense_id` (`/expenses/<int:expense_id>/delete`) so it doesn't shadow the
builtin and matches `edit_expense`. Update the function signature to match.

### Access rules
Apply these in order on **both** GET and POST:
1. No `session["user_id"]` → `302` to `url_for('login')`. Nothing is read or
   deleted.
2. Stale session (user deleted) → `_session_user()` clears it → `302` to
   `login`.
3. Look up the expense with `get_expense_by_id(expense_id, user_id)`, scoped
   to the session user. If the result is `None`, call `abort(404)`. That
   covers both "doesn't exist" and "belongs to someone else". Never return 403.
4. **POST only:** if `_csrf_valid(request.form)` is false, call `abort(400)`.
   Nothing is deleted. This check runs after the login and ownership checks.
5. **POST only:** call `delete_expense_row(expense_id, user_id)`, using the
   name below. If it returns `False` (the row was already deleted, e.g. by a
   double submit or another tab), call `abort(404)`.
6. `user_id` **always** comes from the session. Ignore any `user_id` or `id`
   field in the form body.

A non-integer id (`/expenses/abc/delete`) already returns 404 through Flask's
`int` converter. Other methods (`PUT`, `DELETE`) get Flask's automatic `405`.

## Database changes
No schema changes. Verified against `database/db.py`: `expenses` already has
`id` and `user_id` (FK → `users.id`). No other table references `expenses`,
so deleting a row needs no cascade.

**New helper** in `database/db.py`:

```python
def delete_expense_row(expense_id, user_id):
    """Delete one expense owned by ``user_id``. Return True if a row was deleted."""
```

- SQL: `DELETE FROM expenses WHERE id = ? AND user_id = ?`, then commit and
  return `cur.rowcount == 1`.
- It uses `get_db()`, closes in `finally`, and uses static `?`-parameterised
  SQL, the same as `update_expense`.
- It is named `delete_expense_row`, not `delete_expense`, so the import
  doesn't clash with the `delete_expense` route function in `app.py`.

## Templates
- **Create:**
  - `templates/delete_expense.html`: extends `base.html`, with title
    "Delete expense — Spendly". It loads `css/expense.css` in
    `{% block head %}`. It uses the same page structure as
    `edit_expense.html`:
    1. A heading "Delete expense" and a subtitle warning that the action can't
       be undone.
    2. A summary card listing the expense: date (formatted `DD Mon YYYY`),
       description (or the category when it is empty), category, and amount
       (`₹` with 2 dp).
    3. `<form method="POST" action="{{ url_for('delete_expense',
       expense_id=expense_id) }}">` with only the hidden `csrf_token` input.
    4. Actions: a "Cancel" link to `url_for('profile')` and a submit button
       "Delete expense" with a danger style (`btn-danger`).
    5. Autoescaping only, never `|safe`.
- **Modify:**
  - `templates/profile.html`: in the existing actions cell, add a second link
    after Edit:
    `<a href="{{ url_for('delete_expense', expense_id=t.id) }}"
    class="profile-delete-link" aria-label="Delete {{ t.description or
    t.category }} on {{ t.date }}">Delete</a>`. A Lucide `trash-2` icon is
    optional. This is a plain link to the confirmation page (GET), not a form.

## Files to change
- `app.py`:
  - Import `delete_expense_row` from `database.db`.
  - Add a small `_expense_summary(row)` helper that turns a DB row into
    display values: `date` via `_format_date`, `description` (falls back to
    the category), `category`, and `amount` as a float.
  - Replace the `delete_expense` stub with the GET/POST handler described
    above. Keep it thin: no SQL, and no validation beyond the CSRF check.
  - Update the comment on `app.config` so it mentions that the delete form
    also carries the CSRF token.
- `database/db.py`: add `delete_expense_row()`.
- `templates/profile.html`: add the delete link described above.
- `static/css/profile.css`: add `.profile-delete-link` (it mirrors
  `.profile-edit-link` but uses `--danger` / `--danger-light`). Widen the
  actions column if needed so both links fit, including at ~375px.
- `static/css/expense.css`: add the confirmation summary card styles and
  `.btn-danger` (`--danger` background, `--paper-card` text,
  `:hover`/`:focus-visible` states), using only `:root` tokens.
- `CLAUDE.local.md`: change the routes-table row to
  `GET/POST /expenses/<id>/delete` | Implemented — Step 9 (login required,
  owner only, POST + CSRF to delete).
- `README.md`: update the `/expenses/<id>/delete` row to `GET/POST` |
  Implemented.

## Files to create
- `.claude/specs/09-delete-expenses.md` (this spec)
- `templates/delete_expense.html`
- `tests/test_09-delete-expenses.py`: pytest tests that use the existing
  `app`/`client` fixtures in `tests/conftest.py`.

## New dependencies
No new dependencies. Use Flask plus the standard library only.

## Rules for implementation
- No SQLAlchemy or ORMs. Use raw `sqlite3` through `get_db()` only.
- Parameterised queries only (`?` placeholders). Never use f-strings, `%` or
  `.format()` to build SQL.
- Passwords hashed with werkzeug. This step touches no passwords.
- Use CSS variables and never hardcode hex values. No inline `<style>` tags or
  `style=""` attributes.
- All templates extend `base.html`.
- All SQL lives in `database/db.py`. `app.py` only checks access, calls
  helpers, and renders or redirects.
- **GET never deletes.** Only a `POST` with a valid CSRF token deletes.
- **The ownership check is done in SQL** (`WHERE id = ? AND user_id = ?`) for
  both the lookup and the delete. Never delete by id alone, and never trust an
  id or user_id from the form.
- Another user's expense, a missing expense, and an already-deleted expense
  all return **404** through `abort(404)`, never a string return and never
  403.
- Reuse `get_expense_by_id`, `_csrf_token` and `_csrf_valid` from Step 8. Do
  not fork them.
- Use `url_for()` for every link, the form `action`, and the redirect. Never
  hardcode `/expenses/...` or `/profile`.
- Use Post/Redirect/Get: a successful POST always redirects.
- No JavaScript is required. Don't use `confirm()` dialogs. The confirmation
  page is the confirmation, and it works with JS disabled.
- Do not change add or edit behaviour, or their tests.
- Keep the app on port 5001.

## Definition of done
- [ ] Logged out, `GET` and `POST /expenses/1/delete` both redirect to `/login`, and the expense still exists
- [ ] Logged in as the demo user, every row in "Recent transactions" on `/profile` has a "Delete" link to `/expenses/<that row's id>/delete` next to "Edit"
- [ ] Clicking "Delete" on "Lunch" shows a confirmation page with its date, "Lunch", Food and ₹12.50, plus "Cancel" and "Delete expense" buttons
- [ ] Visiting the confirmation page (GET) any number of times deletes nothing
- [ ] "Cancel" returns to `/profile` with the expense still there
- [ ] Confirming redirects to `/profile`, where the Lunch row is gone, the total drops by ₹12.50, the transaction count drops by 1, and the Food share of the category breakdown updates
- [ ] Deleting the last expense in a category removes that category from the breakdown, and deleting every expense shows the profile's empty state without errors
- [ ] Submitting the same delete again (double submit or back button) → 404, and no other row is affected
- [ ] User B requesting `GET` or `POST /expenses/<user A's expense id>/delete` (with B's own valid CSRF token) gets 404, and user A's expense still exists
- [ ] `GET /expenses/999999/delete` → 404; `GET /expenses/abc/delete` → 404
- [ ] A POST with a missing or wrong `csrf_token` → 400, and the expense still exists
- [ ] A forged `user_id` field in the POST body has no effect. Only the session user's expense can be deleted
- [ ] A stale session (user deleted) on the delete route clears the session and redirects to `/login`
- [ ] No SQL strings in `app.py`. `delete_expense_row` uses static `?`-parameterised SQL with `user_id` in the `WHERE` clause
- [ ] The confirmation page reuses `expense.css`, uses only CSS variables, and stacks cleanly at ~375px wide. The profile table's Edit and Delete links don't break the mobile layout
- [ ] The add and edit forms and their tests behave exactly as before
- [ ] App runs on port 5001, and `pytest` passes, including `tests/test_09-delete-expenses.py` and every existing test unchanged
