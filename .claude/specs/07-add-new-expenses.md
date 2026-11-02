# Spec: Add New Expenses

## Overview
Through Step 6, users can only view expenses: the seeded demo data and
anything inserted by hand. `/profile` already shows an "Add expense" button
that points at `url_for('add_expense')`, but that route is still a stub that
returns a plain string. This step turns `/expenses/add` into a working
feature. A logged-in user gets a form with amount, category, date and an
optional description. The server validates it, stores a new row in
`expenses` for that user, and redirects to `/profile`, where the new expense
appears in the stats, recent transactions and category breakdown. This is the
first write path for expenses and comes before edit (Step 8) and delete
(Step 9), which reuse the same validation and form layout.

## Depends on
- **Step 1 — Database setup** (complete): the `expenses` table, the
  `CATEGORIES` tuple, and `get_db()` with `PRAGMA foreign_keys = ON`.
- **Step 3 — Login and Logout** (complete): `session["user_id"]`.
- **Step 4 — Profile Page Design** (complete): the "Add expense" button on
  `profile.html` that links to `url_for('add_expense')`.
- **Step 5 — Backend Routes for Profile Page** (complete): `/profile` reads
  real data, so a newly added expense shows up straight away.
- **Step 6 — Date Filter** (complete): `_parse_iso_date()` in `app.py`, which
  this step reuses to validate the date field.

## Routes
- `GET /expenses/add` — renders the add-expense form. The date field
  defaults to today and the category to the first entry in `CATEGORIES`.
  — logged-in
- `POST /expenses/add` — validates the form. If it is valid, inserts the
  expense for `session["user_id"]` and returns a `302` redirect to
  `url_for('profile')`. If it is invalid, re-renders the form with HTTP `400`,
  one error message, and the submitted values kept. — logged-in

Both methods live on the **existing** `add_expense` endpoint. Keep the
function name `add_expense` so `url_for('add_expense')` in `profile.html`
keeps working. Change the decorator to `methods=["GET", "POST"]`.

### Access rules
- No `session["user_id"]` → `302` redirect to `url_for('login')` for both GET
  and POST. Nothing is inserted.
- A session that points at a user who no longer exists (`get_user_by_id`
  returns `None`) → `session.clear()` and redirect to `login`, the same as
  `/profile`.
- `user_id` **always** comes from the session. Ignore any `user_id` field in
  the form.

### Validation rules (POST)
Check the fields in this order and report only the **first** error:

| Field | Rule | Error message |
|---|---|---|
| `amount` | Required. Strip whitespace. Must parse as a number with `float()`, be finite (not `nan`/`inf`), be `> 0`, and be `<= 1_000_000`. Round to 2 decimal places before storing. | "Enter an amount greater than 0." (missing, non-numeric, not finite, or ≤ 0) / "Amount is too large." (> 1,000,000) |
| `category` | Required. Must be **exactly** one of `CATEGORIES` from `database/db.py`. | "Choose a valid category." |
| `date` | Required. Must parse as `YYYY-MM-DD` (reuse `_parse_iso_date`). Must not be later than `date.today()`. | "Enter a valid date." / "Date cannot be in the future." |
| `description` | Optional. Strip whitespace. Empty → store `NULL`. Max 200 characters after stripping. | "Description must be 200 characters or fewer." |

Put the error strings in module-level constants, as Steps 2, 3 and 6 do.
Put the validation in one pure helper, for example
`_parse_expense_form(form, today) -> (values: dict | None, error: str | None)`.
It must run no SQL and take `today` as a parameter so tests can control it.
Steps 8 and 9 will reuse it.

## Database changes
No database changes. Verified against `database/db.py`: `expenses` already
has `user_id` (FK → `users.id`), `amount REAL NOT NULL`,
`category TEXT NOT NULL`, `date TEXT NOT NULL`, `description TEXT` (nullable),
and `created_at` with a default. No new tables, columns or indexes are needed.

**New helper** in `database/db.py`:

```python
def create_expense(user_id, amount, category, date, description=None):
    """Insert one expense for ``user_id`` and return its id."""
```

- One static, parameterised `INSERT INTO expenses (user_id, amount, category,
  date, description) VALUES (?, ?, ?, ?, ?)`.
- Use `get_db()`, `commit()`, and close in `finally`, the same as
  `create_user`.
- Return `cur.lastrowid`.
- Do not catch `sqlite3.IntegrityError`. The route has already confirmed the
  user exists, so an FK failure is a real bug and should surface.

## Templates
- **Create:**
  - `templates/add_expense.html`: extends `base.html`, with title
    "Add expense — Spendly". It loads `css/expense.css` in `{% block head %}`.
    The layout is a centred card with:
    1. A heading "Add an expense" and a short subtitle.
    2. An error banner `<div class="expense-error" role="alert">`, rendered
       only when `error` is set.
    3. `<form method="POST" action="{{ url_for('add_expense') }}">` with:
       - `amount`: `<input type="number" name="amount" step="0.01"
         min="0.01" max="1000000" inputmode="decimal" required>`, prefixed
         with a visible `₹`.
       - `category`: a `<select name="category" required>` built by looping
         over `categories`, with the submitted value (or the default)
         `selected`.
       - `date`: `<input type="date" name="date" max="{{ today }}" required>`,
         defaulting to today.
       - `description`: `<input type="text" name="description"
         maxlength="200">`, optional.
       - Every input has a `<label for=...>`.
       - A submit button "Add expense" and a "Cancel" link to
         `url_for('profile')`.
    4. Sticky values: after a failed POST, every field shows what the user
       typed. Rely on autoescaping and never use `|safe`.
- **Modify:**
  - None. `profile.html` already links to `url_for('add_expense')`.

## Files to change
- `app.py`:
  - Import `CATEGORIES` and `create_expense` from `database.db`.
  - Add the error-message constants and the pure `_parse_expense_form`
    helper described above.
  - Replace the `add_expense` stub with a `GET`/`POST` handler. It checks the
    login and stale session, then on GET renders the form with defaults. On
    POST it validates, then either re-renders with `400` or calls
    `create_expense(...)` and redirects to `profile`. Keep the route thin, with
    no SQL in it.
  - Leave the edit and delete stubs untouched.
- `database/db.py`: add `create_expense()`.
- `CLAUDE.local.md`: change the `/expenses/add` row in the routes table to
  `GET/POST /expenses/add` | Implemented — Step 7 (login required).
- `README.md`: update the `/expenses/add` row from "Placeholder" to
  implemented.

## Files to create
- `.claude/specs/07-add-new-expenses.md` (this spec)
- `templates/add_expense.html`
- `static/css/expense.css`: page-specific styles for the add form (card,
  field grid, the `₹` amount prefix, the select, the error banner, and the
  action row). Use only `:root` tokens from `style.css`. Reuse the existing
  `.form-group`, `.form-input`, `.btn-primary` and `.btn-ghost` classes
  where they fit. Stack to one column at about 375px wide. Edit (Step 8) will
  reuse this file.
- `tests/test_07-add-new-expenses.py`: pytest tests that use the existing
  `app`/`client` fixtures in `tests/conftest.py`.

## New dependencies
No new dependencies. Use only Flask and the standard library (`datetime`,
`math.isfinite`).

## Rules for implementation
- No SQLAlchemy or ORMs. Use raw `sqlite3` through `get_db()` only.
- Parameterised queries only (`?` placeholders). Never use f-strings, `%` or
  `.format()` to build SQL.
- Passwords hashed with werkzeug. This step touches no passwords.
- Use CSS variables and never hardcode hex values. All new styles go in
  `expense.css`, with no inline `<style>` tags or `style=""` attributes.
- All templates extend `base.html`.
- All SQL lives in `database/db.py`. `app.py` only validates input, calls
  helpers, and renders or redirects.
- Use `url_for()` for every link, the form `action`, and the redirect. Never
  hardcode `/expenses/add` or `/profile`.
- Use Post/Redirect/Get: a successful POST always redirects and never renders
  directly.
- Server-side validation is the source of truth. HTML attributes (`required`,
  `min`, `max`, `maxlength`) only help the user, and the server must reject
  the same bad input when those attributes are bypassed.
- Bad input never causes a 500. Every invalid case returns `400` with the
  form re-rendered.
- The category allow-list is `CATEGORIES` from `database/db.py`. Do not
  duplicate the list in `app.py` or the template.
- No JavaScript is required. The form must work with JS disabled. If you add
  any JS, it must be vanilla and live in `static/js/main.js`.
- CSRF protection is out of scope because no new packages are allowed. Do not
  add Flask-WTF.
- Do not implement edit (Step 8) or delete (Step 9).
- Keep the app on port 5001.

## Definition of done
- [ ] Logged out, `GET /expenses/add` and `POST /expenses/add` both redirect to `/login`, and the POST inserts nothing
- [ ] Logged in as the demo user, clicking "Add expense" on `/profile` opens the form with amount, category (all 7 categories), date (defaulting to today), and description fields
- [ ] Submitting `amount=250, category=Food, date=<today>, description=Dinner` redirects to `/profile`, which now shows 9 transactions, a total of ₹472.19, and "Dinner" at the top of recent transactions
- [ ] The new row in `expenses` has the logged-in user's `user_id`, `amount` rounded to 2 dp, and the submitted category and date
- [ ] Leaving the description blank stores `NULL`, and the expense still shows on `/profile`
- [ ] `amount` that is empty, `0`, `-5`, `abc`, `nan` or `inf` → HTTP 400, "Enter an amount greater than 0.", and nothing inserted
- [ ] `amount=1000001` → HTTP 400 "Amount is too large."
- [ ] `category=Crypto` (not in `CATEGORIES`) → HTTP 400 "Choose a valid category."
- [ ] `date=2026-13-45` or empty → HTTP 400 "Enter a valid date."; tomorrow's date → HTTP 400 "Date cannot be in the future."
- [ ] A description longer than 200 characters → HTTP 400 with the length error
- [ ] After any failed POST, the form keeps the submitted amount, category, date and description
- [ ] A forged `user_id` field in the POST body is ignored, and the expense is saved to the session user
- [ ] An expense added by user A never appears on user B's `/profile`
- [ ] A stale session (user deleted) on `/expenses/add` clears the session and redirects to `/login`
- [ ] Adding an expense dated in last month makes it appear under the "Last month" preset on `/profile` and not under "This month"
- [ ] No SQL strings in `app.py`, and `create_expense` uses a static `?`-parameterised INSERT
- [ ] `expense.css` uses only CSS variables, and the form stacks cleanly on a ~375px-wide screen
- [ ] The edit and delete routes are still stubs
- [ ] App runs on port 5001, and `pytest` passes, including `tests/test_07-add-new-expenses.py` and every existing test unchanged
