# Spec: Login and Logout

## Overview
This step makes authentication work end to end. Users can already register
(Step 2), but `GET /login` only renders a form that posts to a route which does
not accept POST, and `/logout` is a raw-string stub. This feature adds a
`POST /login` handler that looks the user up by email, verifies the password
with werkzeug's `check_password_hash`, and stores the user's id and name in
Flask's signed `session` cookie. `GET /logout` clears the session and redirects
to the landing page. The navbar in `base.html` becomes session-aware so a
logged-in user sees their name and a "Sign out" link instead of "Sign in" /
"Get started". Sessions are the prerequisite for every remaining roadmap step —
the profile page (Step 4) and all expense routes (Steps 7–9) need to know who
the current user is.

## Depends on
- **Step 1 — Database setup** (complete): `get_db()`, the `users` table, and the
  seeded demo user `demo@spendly.com` / `demo123`.
- **Step 2 — Registration** (complete): `get_user_by_email(email)` in
  `database/db.py`, and users stored with werkzeug password hashes.

## Routes
- `GET /login` — render the sign-in form (already implemented; now shares a
  handler with POST). If the user is already logged in, redirect to `profile` — public
- `POST /login` — validate credentials; on success set the session and redirect
  to `profile`; on failure re-render `login.html` with an `error` — public
- `GET /logout` — clear the session and redirect to `landing` (replaces the
  raw-string stub) — public (safe to hit when logged out; just redirects)

## Database changes
No database changes. The existing `users` table already holds `email` and
`password_hash`.

No new DB helpers are required — reuse `get_user_by_email(email)`.
Password verification (`check_password_hash`) is not a DB operation and may be
called from the route or a small helper in `app.py`.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html`
    - Change `action="/login"` to `action="{{ url_for('login') }}"`
    - Re-fill the email input after an error (`value="{{ email or '' }}"`);
      never re-fill the password
  - `templates/base.html`
    - Navbar: when `session.get('user_id')` is set, show the user's name
      (`session['user_name']`) and a "Sign out" link to `url_for('logout')`;
      otherwise keep the existing "Sign in" / "Get started" links

## Files to change
- `app.py`
  - Import `session` from flask (and `check_password_hash` from `werkzeug.security`)
  - Set `app.secret_key` from `os.environ.get("SECRET_KEY")`, falling back to a
    clearly-labelled dev-only default string
  - Change `/login` to `methods=["GET", "POST"]` and add POST handling
  - Replace the `/logout` stub with the real implementation
- `templates/login.html` — `url_for` form action, email re-fill
- `templates/base.html` — session-aware navbar
- `static/css/style.css` — only if the navbar user name needs styling; any new
  rule must use existing CSS variables

## Files to create
- `.claude/specs/03-login-logout.md` (this spec)

## New dependencies
No new dependencies. `flask.session` and `werkzeug.security.check_password_hash`
are already available via `requirements.txt`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders) — never f-strings in SQL
- Passwords hashed with werkzeug — verify with `check_password_hash`, never
  compare plain text
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- All DB access lives in `database/db.py`; the route only calls helpers
- Use `url_for()` for every internal link and redirect
- Login input handling:
  - Strip and lowercase `email` (matches how Step 2 stores it); do not strip `password`
  - Either field empty → "Email and password are required." (HTTP 400)
  - Unknown email **or** wrong password → the same generic message
    "Invalid email or password." (HTTP 401) — never reveal which one was wrong
  - Do **not** enforce the 8-character minimum on login (the seeded demo
    password `demo123` is 7 characters)
- On success: `session.clear()` first (avoid session fixation), then set
  `session["user_id"]` and `session["user_name"]`, then redirect
- Logout: `session.clear()` then `redirect(url_for("landing"))`
- Do not implement the profile page — `/profile` stays a Step 4 stub; it is only
  used as the post-login redirect target
- Do not add a `login_required` decorator or protect other routes yet — that
  belongs with the steps that implement those routes
- Do not touch the expense stub routes
- Keep the app on port 5001

## Definition of done
- [ ] `GET /login` renders the form with no error shown
- [ ] Logging in as `demo@spendly.com` / `demo123` redirects to `/profile` and sets `user_id` in the session
- [ ] Logging in with ` DEMO@Spendly.com ` (mixed case + whitespace) also succeeds
- [ ] A user registered via `/register` can then log in with their credentials
- [ ] Wrong password shows "Invalid email or password." with status 401 and no session is set
- [ ] Unknown email shows the exact same "Invalid email or password." message with status 401
- [ ] Submitting with an empty field shows "Email and password are required." with status 400
- [ ] After a failed login the email is re-filled and the password field is empty
- [ ] While logged in, the navbar shows the user's name and "Sign out"; "Sign in" / "Get started" are hidden
- [ ] While logged in, `GET /login` redirects to `/profile`
- [ ] `GET /logout` clears the session and redirects to `/`; the navbar shows "Sign in" again
- [ ] `GET /logout` while logged out redirects to `/` without error
- [ ] The login form `action` is rendered via `url_for` (no hardcoded `/login` in the template)
- [ ] App runs on port 5001 and all existing tests in `tests/` still pass
