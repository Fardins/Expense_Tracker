# Spec: Profile Page Design

## Overview
After Step 3, a successful login redirects to `/profile`, but that route still
returns the raw string "Profile page — coming in Step 4". This step replaces the
stub with a real, logged-in-only profile page that matches the Spendly visual
language (DM Serif Display / DM Sans, paper and ink palette, cards). The focus
of this step is **the page design and layout**: a user info card, a row of
summary stat cards, a recent-transactions table, and a spending-by-category
breakdown. The user's name comes from the session. Everything else (email,
member-since date, totals, transactions, category breakdown) is **hardcoded
placeholder data defined in the route**, so the layout can be built and
reviewed before the database queries are wired in by a later step. The page is
also the first route that requires login, so it introduces the redirect for
anonymous visitors.

## Depends on
- **Step 1 — Database setup** (complete): schema and `CATEGORIES` in
  `database/db.py` (category names used in the placeholder data).
- **Step 2 — Registration** (complete).
- **Step 3 — Login and Logout** (complete): `session["user_id"]` and
  `session["user_name"]` are set on login; `/login` already redirects to
  `profile`.

## Routes
- `GET /profile` — render `profile.html` with the session user's name plus
  hardcoded placeholder data; redirect to `login` if not logged in — logged-in

No other new routes.

## Database changes
No database changes. Verified against `database/db.py`: the `users` and
`expenses` tables already contain every field the page will eventually show
(`name`, `email`, `created_at`, `amount`, `category`, `date`, `description`).
No new DB helpers in this step. Real queries come in the step that connects the
profile page to the database.

## Templates
- **Create:**
  - `templates/profile.html`: extends `base.html`, sets `{% block title %}`
    and loads `profile.css` via `{% block head %}`. Sections, top to bottom:
    1. **User info card:** avatar circle with the user's initial, name, email,
       "Member since" date.
    2. **Summary stats:** three cards: Total spent, Number of transactions,
       Top category.
    3. **Recent transactions:** table with Date, Description, Category (as a
       pill/badge), Amount (right-aligned, formatted with `₹` and 2 decimals).
       Show an empty-state message when the list is empty.
    4. **Spending by category:** one row per category with name, amount, and
       a horizontal bar whose width is the category's percentage of the total
       (set via an inline `style="width: N%"` value only, no other inline styles).
    5. **Actions:** "Add expense" button linking to `url_for('add_expense')`.
- **Modify:**
  - `templates/base.html`: make the navbar user name a link to
    `url_for('profile')` (keep the existing `nav-user` class).

## Files to change
- `app.py`: replace the `/profile` stub with a route that:
  - redirects to `url_for("login")` when `session.get("user_id")` is missing
  - builds placeholder dicts/lists (`user`, `stats`, `transactions`,
    `categories`) and passes them to `render_template("profile.html", ...)`
  - takes the user's name from `session["user_name"]`
- `templates/base.html`: navbar name links to profile
- `static/css/style.css`: only if a shared style (e.g. a link style for
  `.nav-user`) is needed. Profile-specific rules go in `profile.css`

## Files to create
- `templates/profile.html`
- `static/css/profile.css`
- `.claude/specs/04-profile-page-design.md` (this spec)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (no queries are expected in this step)
- Passwords hashed with werkzeug (no password handling in this step)
- Use CSS variables. Never hardcode hex values. Reuse the `:root` tokens in
  `style.css` (`--paper-card`, `--border`, `--accent`, `--accent-light`,
  `--ink-muted`, `--radius-md`, `--font-display`, etc.)
- All templates extend `base.html`
- Page-specific styles go in `static/css/profile.css`, linked via
  `{% block head %}`. No `<style>` tags, no inline styles except the bar
  width percentage
- `url_for()` for every internal link and redirect. No hardcoded URLs
- No DB logic in the route. Placeholder data is plain Python literals
- Placeholder categories must come from the existing `CATEGORIES` names
  (Food, Transport, Bills, Health, Entertainment, Shopping, Other)
- Placeholder totals must be internally consistent: the total equals the sum of
  the category amounts, and category percentages add up to about 100
- Currency is shown as `₹` with two decimals (use a Jinja format filter, e.g.
  `"%.2f"|format(amount)`)
- Escape all user-supplied text. Rely on Jinja autoescaping; never use `|safe`
  on the user's name
- No JavaScript is required. If any is added, vanilla JS in `static/js/main.js` only
- Layout must be responsive: stat cards and sections stack into one column on
  narrow screens (extend the existing responsive breakpoint pattern)
- Do not implement the expense routes (`/expenses/add`, edit, delete stay stubs)
- Do not add a generic `login_required` decorator yet. Inline the session check
  in this route
- Keep the app on port 5001

## Definition of done
- [ ] Visiting `/profile` while logged out redirects to `/login`
- [ ] Logging in as `demo@spendly.com` / `demo123` lands on `/profile` and the page renders (HTTP 200, not a raw string)
- [ ] The page shows the logged-in user's name from the session and an avatar with their initial
- [ ] The user info card shows an email and a "Member since" date
- [ ] Three summary stat cards are visible: Total spent, Transactions, Top category
- [ ] The recent-transactions table shows date, description, category badge and a right-aligned `₹` amount with 2 decimals
- [ ] The spending-by-category section shows one bar per category with widths proportional to amount
- [ ] The total spent equals the sum of the category amounts shown
- [ ] The "Add expense" button links to `/expenses/add` (rendered via `url_for`)
- [ ] The navbar user name links to `/profile`
- [ ] The page uses `profile.css`, and no hex colours appear in `profile.css` or `profile.html`
- [ ] At a narrow viewport (~375px) the cards and sections stack into one column with no horizontal scroll
- [ ] Logging out from the profile page returns to `/`, and `/profile` then redirects to `/login` again
- [ ] App runs on port 5001 and all existing tests in `tests/` still pass
