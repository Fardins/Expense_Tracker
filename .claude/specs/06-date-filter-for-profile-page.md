# Spec: Date Filter for Profile Page

## Overview
After Step 5, `/profile` shows real data, but always for **all time**. The
summary stats, recent transactions and spending-by-category breakdown cover
every expense the user has ever logged. This step adds a date filter so users
can limit the dashboard to a period. The filter offers a few presets (All
time, This month, Last month, Last 3 months) and a custom range with "From"
and "To" date fields. The filter is a plain `GET` form that writes `from` and
`to` query parameters, so filtered views can be bookmarked and shared without
any JavaScript. All three data sections use the same range. The filtering runs
in SQL through optional parameters on the existing helpers in
`database/db.py`. This comes before add, edit and delete (Steps 7–9) because
it only reads data and reuses the queries Step 5 just added.

## Depends on
- **Step 1 — Database setup** (complete): the `expenses.date` column is stored
  as ISO `YYYY-MM-DD` text, so string comparison (`>=`, `<=`) matches
  date order.
- **Step 3 — Login and Logout** (complete): `session["user_id"]`.
- **Step 4 — Profile Page Design** (complete): `profile.html`, `profile.css`,
  and the visual language.
- **Step 5 — Backend Routes for Profile Page** (complete):
  `get_recent_expenses`, `get_expense_summary`, `get_category_totals`, and the
  `_build_*` helpers in `app.py`.

## Routes
- `GET /profile` — existing route, now reads the optional query parameters
  `from` and `to` (both `YYYY-MM-DD`) and limits the stats, transactions and
  categories to that inclusive range. If neither is given, the page shows all
  time, exactly as Step 5 does. — logged-in

No new routes.

### Query parameter rules
- Each of `from` and `to` is optional. Only `from` means "on or after". Only
  `to` means "on or before".
- An empty string counts as missing.
- A value that does not parse as a `YYYY-MM-DD` date is **ignored** (treated
  as missing). The page still renders with HTTP 200 and shows an inline error
  message: "Invalid date — showing all time." Never return a 500.
- If `from` is later than `to`, ignore **both** values and show the error
  "Start date must be on or before end date." The page renders with HTTP 200
  and shows all time.
- `user_id` always comes from the session and never from query parameters.

### Presets
The presets are computed in `app.py` from `date.today()`. Each one is a link
built with `url_for('profile', **params)`:

| Preset        | `from`                         | `to`                       |
|---------------|--------------------------------|----------------------------|
| All time      | — (no params)                  | —                          |
| This month    | 1st of the current month       | today                      |
| Last month    | 1st of the previous month      | last day of previous month |
| Last 3 months | 1st of the month 2 months ago  | today                      |

The preset whose `from`/`to` exactly match the active range gets an active
state, `profile-filter-preset--active` with `aria-current="true"`. If no
preset matches, the range is a custom one and no preset is marked active.

## Database changes
No database changes. Verified against `database/db.py`: `expenses.date` is
`TEXT NOT NULL` and stores ISO dates, so no new columns, tables or indexes are
needed.

**Query helper changes** (signatures only, no schema change). Add
keyword-only `date_from=None, date_to=None` to:
- `get_recent_expenses(user_id, limit=10, *, date_from=None, date_to=None)`
- `get_expense_summary(user_id, *, date_from=None, date_to=None)`
- `get_category_totals(user_id, *, date_from=None, date_to=None)`

Each helper uses **static SQL**. Never build SQL text with string formatting.
Use the null-check pattern so a single query handles every combination:

```sql
WHERE user_id = ?
  AND (? IS NULL OR date >= ?)
  AND (? IS NULL OR date <= ?)
```

and pass the parameters `(user_id, date_from, date_from, date_to, date_to)`.
Calls that pass no dates must behave exactly as in Step 5.

## Templates
- **Create:** none
- **Modify:**
  - `templates/profile.html`: add a filter bar between the user card and the
    summary stats, as `<section class="profile-card profile-filter"
    aria-label="Date filter">`, containing:
    1. A preset row of `<a>` links (All time / This month / Last month /
       Last 3 months). Every href comes from `url_for('profile', ...)`.
    2. A `<form method="get" action="{{ url_for('profile') }}">` with two
       `<input type="date">` fields named `from` and `to`, pre-filled with
       the active values, plus an "Apply" submit button. When a filter is
       active, also show a "Clear" link to `url_for('profile')`.
    3. An error line `<p class="profile-filter-error" role="alert">` that is
       rendered only when `filter.error` is set.
    4. A range caption such as "Showing 01 Oct 2026 – 31 Oct 2026" or
       "Showing all time", using `_format_date` output.
  - Change the empty-state text to depend on the filter. When a range is
    active and has no data, show "No transactions in this period." and
    "No spending in this period." instead of the Step 5 wording.
  - Do not remove or rename any existing classes or test hooks
    (`profile-name`, `profile-total-spent`, `profile-top-category`, and so on).

## Files to change
- `app.py`:
  - Add `_parse_date_filter(args)`. It is a pure function with no SQL and
    returns `{'date_from': str|None, 'date_to': str|None, 'error': str|None}`
    using the rules above. Validate with `datetime.strptime(v, "%Y-%m-%d")`.
  - Add `_date_presets(today)`. It is a pure function that returns a list of
    `{'label', 'from', 'to'}`. Take `today` as a parameter so tests can
    control the date.
  - Update `_build_transactions`, `_build_stats` and `_build_categories` to
    accept `date_from` and `date_to` and pass them through to the DB helpers.
  - In `profile()`, parse the filter once, pass it to all three builders, and
    add `filter` (the active from/to, error, presets, active preset label,
    and caption) to the template context.
  - Keep `profile()` thin. It parses, builds and renders, nothing more.
- `database/db.py`: add the optional date arguments to the three helpers as
  described above.
- `templates/profile.html`: the filter bar and empty-state wording.
- `static/css/profile.css`: styles for `.profile-filter`, the preset links and
  their active state, the date inputs, the error line, and the caption. Use
  only the existing `:root` tokens and stack the layout on mobile.
- `tests/test_profile.py`: add tests for the filter. Existing tests must keep
  passing unchanged.
- `CLAUDE.local.md`: add a row or note recording that `/profile` supports the
  `?from=&to=` date filter (Step 6).

## Files to create
- `.claude/specs/06-date-filter-for-profile-page.md` (this spec)

## New dependencies
No new dependencies. Use only `datetime` and `date` from the standard library.

## Rules for implementation
- No SQLAlchemy or ORMs. Use raw `sqlite3` through `get_db()` only.
- Parameterised queries only (`?` placeholders). Never use f-strings, `%` or
  `.format()` to build SQL, and never concatenate SQL conditions. Use the
  static `(? IS NULL OR ...)` pattern.
- Passwords hashed with werkzeug. This step touches no passwords.
- Use CSS variables and never hardcode hex values. All new styles go in
  `profile.css`, with no inline `<style>` tags.
- All templates extend `base.html`.
- All SQL lives in `database/db.py`. `app.py` only validates input and shapes
  the context.
- Filtering, summing and grouping happen in SQL, never by filtering
  Python lists.
- Date ranges are **inclusive** at both ends.
- Bad input never causes a 500. Invalid dates are ignored and the error is
  shown in the page.
- Use `url_for()` for every link and the form `action`. Never hardcode
  `/profile?...`.
- No JavaScript is needed. The filter must work with JS disabled. If you add
  any JS, it must be vanilla and live in `static/js/main.js`.
- Rely on Jinja autoescaping. Echoed query values go into `value=""`
  attributes and must not use `|safe`.
- Every query stays scoped to `session["user_id"]`.
- Do not implement `/expenses/add`, edit or delete. They stay stubs.
- Keep the app on port 5001.

## Definition of done
- [ ] `/profile` with no query params renders exactly the Step 5 numbers for the demo user (₹222.19, 8 transactions, top category Bills)
- [ ] The filter bar shows four presets, two date inputs, and an Apply button
- [ ] Clicking "This month" sets `?from=<1st of month>&to=<today>`, and the stats, transactions and categories all reflect only that range
- [ ] `/profile?from=X&to=Y` includes expenses dated exactly X and exactly Y (inclusive bounds)
- [ ] Giving only `from`, or only `to`, filters on one side only
- [ ] A range with no expenses shows ₹0.00, 0 transactions, a `—` top category, and the "in this period" empty-state messages, with HTTP 200
- [ ] `?from=not-a-date` renders HTTP 200, shows the "Invalid date" error, and shows all-time data
- [ ] `?from=2026-10-31&to=2026-10-01` (reversed) renders HTTP 200, shows the "Start date must be on or before end date" error, and shows all-time data
- [ ] The active preset is visually highlighted and has `aria-current="true"`. A custom range highlights no preset
- [ ] The date inputs are pre-filled with the active `from` and `to` values after you submit
- [ ] "Clear" returns to `/profile` with no params
- [ ] Category amounts still add up to "Total spent" for every filtered range
- [ ] One user's filtered view never includes another user's expenses (test with two users)
- [ ] A logged-out visit to `/profile?from=...` redirects to `/login`
- [ ] No SQL strings in `app.py`, and every query in `db.py` is static with `?` placeholders
- [ ] `profile.css` uses only CSS variables, and the filter bar stacks cleanly on a ~375px-wide screen
- [ ] App runs on port 5001, and `pytest` passes, including the new filter tests in `tests/test_profile.py`
