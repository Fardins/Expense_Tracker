# Spec: Registration

## Overview
This step makes the existing registration page functional. `GET /register` already
renders `register.html`, but the form posts to a route that does not accept POST.
This feature adds a `POST /register` handler that validates the submitted name,
email and password, hashes the password with werkzeug, stores the new user in the
`users` table via helpers in `database/db.py`, and redirects to the login page on
success. Registration is the first piece of user-facing auth on the Spendly
roadmap — login/logout (Step 3) and the profile page (Step 4) depend on users
being able to create accounts.

## Depends on
- **Step 1 — Database setup** (complete): `get_db()`, `init_db()`, the `users`
  table with `email TEXT NOT NULL UNIQUE`, and `PRAGMA foreign_keys = ON`.

## Routes
- `GET /register` — render the registration form (already implemented; unchanged
  apart from sharing a handler with POST) — public
- `POST /register` — validate input, create the user, redirect to `login` on
  success; re-render `register.html` with an `error` message on failure — public

## Database changes
No database changes. The existing `users` table (`id`, `name`, `email UNIQUE`,
`password_hash`, `created_at`) already covers registration.

New helper functions in `database/db.py` (no schema change):
- `get_user_by_email(email)` — returns a `sqlite3.Row` or `None`
- `create_user(name, email, password)` — hashes the password with
  `generate_password_hash`, inserts the row with a parameterised query, commits,
  returns the new user id. Lets `sqlite3.IntegrityError` propagate for duplicate
  emails so the route can handle the race case.

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html`
    - Change `action="/register"` to `action="{{ url_for('register') }}"`
    - Re-fill `name` and `email` inputs with the submitted values after an error
      (`value="{{ name or '' }}"`, `value="{{ email or '' }}"`); never re-fill the password
    - Add `minlength="8"` to the password input to match server-side validation

## Files to change
- `app.py` — import `request`, `redirect`, `url_for`; change the `/register` route
  to `methods=["GET", "POST"]` and add POST handling
- `database/db.py` — add `get_user_by_email()` and `create_user()`
- `templates/register.html` — `url_for` form action, value re-fill, `minlength`
- `static/css/style.css` — replace the hardcoded `#f5c6c2` border on `.auth-error`
  with a CSS variable (add one to `:root`, e.g. `--danger-border`)

## Files to create
- `.claude/specs/02-registration.md` (this spec)

## New dependencies
No new dependencies. `werkzeug` is already in `requirements.txt`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders) — never f-strings in SQL
- Passwords hashed with werkzeug (`generate_password_hash`) — never store plain text
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- All DB access lives in `database/db.py`; the route only calls helpers
- Use `url_for()` for every internal link and redirect
- Always close DB connections opened by helpers
- Validation (server-side, in order; first failure is shown):
  - Strip whitespace from `name` and `email`; lowercase `email`
  - All three fields required → "All fields are required."
  - Email must contain `@` and a `.` after it → "Please enter a valid email address."
  - Password at least 8 characters → "Password must be at least 8 characters."
  - Email not already registered → "An account with that email already exists."
- On failure, re-render `register.html` with HTTP 400 (409 for a duplicate email)
  and pass `error`, `name`, `email`
- Do not log the user in after registering — sessions belong to Step 3
- Do not touch the `/logout`, `/profile` or expense stub routes

## Definition of done
- [ ] `GET /register` still renders the form with no error shown
- [ ] Submitting valid name/email/password creates a row in `users` and redirects to `/login`
- [ ] The stored `password_hash` is not the plain password and passes `check_password_hash`
- [ ] Submitting with any field empty re-renders the form with "All fields are required."
- [ ] Submitting an invalid email shows "Please enter a valid email address."
- [ ] Submitting a password shorter than 8 characters shows "Password must be at least 8 characters."
- [ ] Registering `demo@spendly.com` (or ` DEMO@Spendly.com `) shows "An account with that email already exists." and creates no new row
- [ ] After an error, name and email are re-filled and the password field is empty
- [ ] The form's `action` is rendered via `url_for` (no hardcoded `/register` in the template)
- [ ] `.auth-error` uses only CSS variables (no hex in the rule)
- [ ] App runs on port 5001 and all existing tests in `tests/test_db.py` still pass
