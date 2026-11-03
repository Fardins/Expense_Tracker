# Spendly — Personal Expense Tracker

Spendly is a lightweight personal expense tracker built with **Flask** and **SQLite**. It helps people log expenses, see where their money goes, and stay on budget, without a spreadsheet.

The project was built step by step with [Claude Code](https://claude.com/claude-code), one spec and one feature branch per step. All nine planned steps are done: accounts, a profile dashboard with date filters, and full add / edit / delete for expenses.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Database](#database)
- [Routes](#routes)
- [Security](#security)
- [Running Tests](#running-tests)
- [Development Guidelines](#development-guidelines)
- [Claude Code Workflow](#claude-code-workflow)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

---

## Features

**Accounts**

- Sign up with name, email, and password (emails are stored lowercase; passwords must be at least 8 characters)
- Log in and log out with a session cookie
- Passwords are hashed with Werkzeug and never shown to templates

**Profile dashboard**

- Profile card with name, email, and "member since" date
- Summary stats: total spent, number of transactions, and top category
- Category breakdown with amounts and percentages
- The 10 most recent transactions, each with edit and delete actions

**Date filter**

- Presets: *All time*, *This month*, *Last month*, *Last 3 months*
- Custom range with inclusive `from` / `to` dates
- Invalid dates or a reversed range fall back to all time with a clear message

**Expenses**

- Add an expense with amount, category, date, and optional description
- Edit any of your own expenses, with the form pre-filled
- Delete an expense from a confirmation page
- Validation: amount must be greater than 0 and at most 1,000,000 (rounded to 2 decimals), category must be one of the fixed list, the date can't be in the future, and descriptions are capped at 200 characters
- On an error, the form keeps what you typed

**Other**

- Responsive landing page, plus Terms and Conditions and Privacy Policy pages
- The database is created and seeded with demo data on first run

---

## Tech Stack

| Layer      | Technology                                   |
| ---------- | -------------------------------------------- |
| Backend    | Python 3.10+, Flask 3.1                      |
| Database   | SQLite (via the standard-library `sqlite3`)  |
| Security   | Werkzeug password hashing, session CSRF tokens |
| Templating | Jinja2                                       |
| Frontend   | HTML, CSS, vanilla JavaScript, Lucide icons (CDN) |
| Testing    | pytest, pytest-flask                         |

The project deliberately has no ORM, no frontend framework, and no build step.

---

## Project Structure

```
Expense_Tracker/
├── app.py                    # Flask app and all routes (single file, no blueprints)
├── database/
│   ├── __init__.py
│   └── db.py                 # Schema, connection helper, seeding, and all queries
├── templates/
│   ├── base.html             # Shared layout; every page extends this
│   ├── landing.html          # Home page
│   ├── register.html
│   ├── login.html
│   ├── profile.html          # Dashboard: stats, categories, transactions, date filter
│   ├── add_expense.html
│   ├── edit_expense.html
│   ├── delete_expense.html   # Delete confirmation
│   ├── terms.html
│   └── privacy.html
├── static/
│   ├── css/
│   │   ├── style.css         # Global styles
│   │   ├── landing.css       # Landing page
│   │   ├── profile.css       # Profile dashboard
│   │   └── expense.css       # Add / edit / delete expense pages
│   └── js/
│       └── main.js           # Vanilla JS (renders Lucide icons)
├── tests/
│   ├── conftest.py           # App fixture wired to a temp database
│   ├── test_db.py
│   ├── test_registration.py
│   ├── test_login_logout.py
│   ├── test_profile.py
│   ├── test_06-date-filter-for-profile-page.py
│   ├── test_07-add-new-expenses.py
│   ├── test_08-edit-expenses.py
│   └── test_09-delete-expenses.py
├── .claude/                  # Claude Code specs, commands, agents, and hooks
├── requirements.txt
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10 or newer
- Git

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/Fardins/Expense_Tracker.git
   cd Expense_Tracker
   ```

2. **Create and activate a virtual environment**

   ```bash
   python -m venv .venv
   ```

   Windows (PowerShell):

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

   macOS / Linux:

   ```bash
   source .venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**

   ```bash
   python app.py
   ```

5. Open **http://127.0.0.1:5001** in your browser.

On first start, the app creates `expense_tracker.db` in the project root and fills it with demo data.

### Demo Account

| Email              | Password  |
| ------------------ | --------- |
| `demo@spendly.com` | `demo123` |

The demo user comes with eight sample expenses, at least one in each category, all dated within the current month. Log in with it to see the dashboard right away, or register your own account.

---

## Configuration

| Setting       | Value                                   | Where                        |
| ------------- | --------------------------------------- | ---------------------------- |
| Port          | `5001`                                  | `app.py`                     |
| Debug mode    | Enabled                                 | `app.py`                     |
| Secret key    | `SECRET_KEY` env var (dev fallback built in) | `app.py`                |
| Database file | `expense_tracker.db` (project root)     | `database/db.py` (`DB_PATH`) |

> **Note:** `python app.py` starts Flask's development server in debug mode. Don't expose it to the internet. For a real deployment, run the app under a production WSGI server such as Gunicorn or Waitress, turn debug mode off, and set a strong `SECRET_KEY` environment variable. Without it, the app falls back to an insecure development key.

---

## Database

The schema is created by `init_db()`. It is safe to run repeatedly, because every table uses `CREATE TABLE IF NOT EXISTS`. Every connection turns on foreign key enforcement (`PRAGMA foreign_keys = ON`).

### `users`

| Column          | Type    | Constraints                    |
| --------------- | ------- | ------------------------------ |
| `id`            | INTEGER | Primary key, autoincrement     |
| `name`          | TEXT    | Not null                       |
| `email`         | TEXT    | Not null, unique               |
| `password_hash` | TEXT    | Not null                       |
| `created_at`    | TEXT    | Defaults to `datetime('now')`  |

### `expenses`

| Column        | Type    | Constraints                          |
| ------------- | ------- | ------------------------------------ |
| `id`          | INTEGER | Primary key, autoincrement           |
| `user_id`     | INTEGER | Not null, references `users(id)`     |
| `amount`      | REAL    | Not null                             |
| `category`    | TEXT    | Not null                             |
| `date`        | TEXT    | Not null, ISO format (`YYYY-MM-DD`)  |
| `description` | TEXT    | Optional                             |
| `created_at`  | TEXT    | Defaults to `datetime('now')`        |

**Categories:** Food, Transport, Bills, Health, Entertainment, Shopping, Other

### Helper functions (`database/db.py`)

All queries use `?` placeholders. Every expense query that takes a `user_id` filters on it in SQL, so one user can never read or change another user's data.

| Function                | Purpose                                                                 |
| ----------------------- | ----------------------------------------------------------------------- |
| `get_db()`              | Returns a connection with `sqlite3.Row` access and foreign keys on. The caller must close it. |
| `init_db()`             | Creates all tables.                                                     |
| `seed_db()`             | Inserts the demo user and sample expenses, but only if `users` is empty. |
| `get_user_by_email()`   | Looks up a user for login and duplicate-email checks.                   |
| `get_user_by_id()`      | Looks up the session user. Never returns `password_hash`.               |
| `create_user()`         | Inserts a user with a hashed password.                                  |
| `create_expense()`      | Inserts an expense.                                                     |
| `get_expense_by_id()`   | Returns an expense only if it belongs to the given user.                |
| `update_expense()`      | Updates an expense owned by the given user.                             |
| `delete_expense_row()`  | Deletes an expense owned by the given user.                             |
| `get_recent_expenses()` | Newest expenses first (default 10), with optional date range.           |
| `get_expense_summary()` | Total spent and transaction count, with optional date range.            |
| `get_category_totals()` | Spending per category, largest first, with optional date range.         |

### Resetting the database

Stop the app, delete `expense_tracker.db`, and start the app again. A fresh database is created and seeded.

---

## Routes

| Method   | Path                    | Description                                   | Login required |
| -------- | ----------------------- | --------------------------------------------- | -------------- |
| GET      | `/`                     | Landing page                                  | No             |
| GET/POST | `/register`             | Create an account, then redirect to login     | No             |
| GET/POST | `/login`                | Log in, then redirect to the profile          | No             |
| GET      | `/logout`               | Clear the session and go to the landing page  | No             |
| GET      | `/profile`              | Dashboard. Accepts `?from=YYYY-MM-DD&to=YYYY-MM-DD` | Yes     |
| GET/POST | `/expenses/add`         | Add an expense                                | Yes            |
| GET/POST | `/expenses/<id>/edit`   | Edit one of your expenses                     | Yes (owner)    |
| GET/POST | `/expenses/<id>/delete` | GET shows a confirmation; POST deletes        | Yes (owner)    |
| GET      | `/terms`                | Terms and Conditions                          | No             |
| GET      | `/privacy`              | Privacy Policy                                | No             |

Logged-out visitors to a protected page are redirected to `/login`. Asking to edit or delete an expense that doesn't exist, or that belongs to someone else, returns **404**.

---

## Security

- **Passwords** are hashed with Werkzeug and checked with `check_password_hash`.
- **Sessions** are cleared on login to prevent session fixation. A session whose user no longer exists is cleared automatically.
- **CSRF:** the session cookie uses `SameSite=Lax`, and the edit and delete forms carry a per-session token that is checked on every POST. A missing or wrong token returns **400**.
- **Ownership:** edit and delete look up the expense by both its id and the logged-in user's id, and the add form takes `user_id` only from the session.
- **Deletes never happen on GET.** The GET request only shows a confirmation page.
- **Request size** is capped at 16 KB (`MAX_CONTENT_LENGTH`).
- **SQL** is always parameterized.

---

## Running Tests

```bash
python -m pytest
```

The suite has **460 tests**. They run against a temporary database (the `app` fixture in `tests/conftest.py` patches `DB_PATH`), so your local `expense_tracker.db` is never touched.

| File                                     | Covers                                                    |
| ---------------------------------------- | --------------------------------------------------------- |
| `test_db.py`                             | Connection settings, schema, seeding, password hashing    |
| `test_registration.py`                   | Sign-up validation and duplicate emails                   |
| `test_login_logout.py`                   | Login, bad credentials, logout, redirects                 |
| `test_profile.py`                        | Profile card, stats, categories, transactions             |
| `test_06-date-filter-for-profile-page.py`| Presets, custom ranges, invalid and reversed dates        |
| `test_07-add-new-expenses.py`            | Add form, validation, sticky values                       |
| `test_08-edit-expenses.py`               | Edit form, ownership, CSRF, validation                    |
| `test_09-delete-expenses.py`             | Confirmation page, ownership, CSRF, double delete         |

Useful variations:

```bash
python -m pytest tests/test_profile.py   # one file
python -m pytest -k "csrf"               # tests whose name matches
python -m pytest -s                      # show print output
```

---

## Development Guidelines

- **Routes** go in `app.py` only. Don't add blueprints.
- **Database logic** goes in `database/db.py` only. Never put it inline in routes.
- **SQL** always uses parameterized queries (`?` placeholders). Never build SQL with f-strings.
- **Templates** extend `base.html` and use `url_for()` for every internal link. Never hardcode URLs.
- **Styles** for a single page go in their own `.css` file, not in inline `<style>` tags.
- **JavaScript** stays vanilla: no frameworks and no npm packages.
- **Errors** use Flask's `abort()` with the right HTTP status code, not a bare error string.
- **Python style** follows PEP 8 with `snake_case` names.
- **Dependencies:** don't add packages to `requirements.txt` without discussing it first.

---

## Claude Code Workflow

The `.claude/` folder holds the setup used to build Spendly with Claude Code.

**Specs** (`.claude/specs/`): one spec per step, `01_database_setup.md` through `09-delete-expenses.md`.

**Slash commands** (`.claude/commands/`):

| Command                | What it does                                                   |
| ---------------------- | -------------------------------------------------------------- |
| `/create_spec`         | Writes the spec for the next step and creates its feature branch |
| `/test_feature`        | Writes and runs tests for a step                               |
| `/code_review_feature` | Runs the security and quality reviewers in parallel            |
| `/ship_feature`        | Commits, pushes, opens a PR, merges, and cleans up             |
| `/seed_user`           | Adds a dummy user to the database                              |
| `/seed_expense`        | Adds realistic dummy expenses for a user                       |

**Subagents** (`.claude/agents/`): `spendly-test-writer`, `spendly-test-runner`, `spendly-security-reviewer`, and `spendly-quality-reviewer`.

**Hooks** (`.claude/settings.json`):

- After Claude writes or edits a `.py` file, it is formatted with `black`.
- Before any shell command or file write, `.claude/hooks/protect_files.py` blocks attempts to delete, move, or overwrite the database, `.env`, or `migrations/`.

---

## Roadmap

- [x] **Step 1:** Database setup (schema, connection helper, seed data)
- [x] Landing, Terms, and Privacy pages
- [x] **Step 2:** User registration
- [x] **Step 3:** Login and logout
- [x] **Step 4:** Profile page design
- [x] **Step 5:** Profile page backed by real data
- [x] **Step 6:** Date filter for the profile page
- [x] **Step 7:** Add expense
- [x] **Step 8:** Edit expense
- [x] **Step 9:** Delete expense

**Possible next steps**

- [ ] CSRF token on the add-expense form (edit and delete already have one)
- [ ] Pagination or a full transaction list (the profile shows the latest 10)

---

## Contributing

1. Fork the repository and create a feature branch:
   ```bash
   git checkout -b feature/your-feature
   ```
2. Follow the [Development Guidelines](#development-guidelines).
3. Add or update tests, and make sure `python -m pytest` passes.
4. Write commit messages in the form `area: short description`, for example `expenses: add delete confirmation page`.
5. Open a pull request against `main`.
