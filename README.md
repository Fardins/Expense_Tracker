# Spendly — Personal Expense Tracker

Spendly is a lightweight personal expense tracker built with **Flask** and **SQLite**. It helps people log expenses, see where their money goes, and stay on budget, without a spreadsheet.

The project is being built step by step with [Claude Code](https://claude.com/claude-code). The data layer, landing page, and static pages are done. Authentication and expense management are next (see [Roadmap](#roadmap)).

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Database](#database)
- [Routes](#routes)
- [Running Tests](#running-tests)
- [Development Guidelines](#development-guidelines)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

---

## Features

**Available now**

- Responsive landing page with product overview and calls to action
- Registration and login pages (UI only)
- Terms and Conditions and Privacy Policy pages
- SQLite data layer with `users` and `expenses` tables, enforced foreign keys, and hashed passwords
- Automatic database creation and demo-data seeding on first run
- Automated test suite for the data layer

**Planned**

- User registration, login, and logout with sessions
- User profile page
- Add, edit, and delete expenses
- Category breakdowns and monthly summaries
- Filtering by date range (last week, last month, custom period)

---

## Tech Stack

| Layer      | Technology                                   |
| ---------- | -------------------------------------------- |
| Backend    | Python 3.10+, Flask 3.1                      |
| Database   | SQLite (via the standard-library `sqlite3`)  |
| Security   | Werkzeug password hashing                    |
| Templating | Jinja2                                       |
| Frontend   | HTML, CSS, vanilla JavaScript                |
| Testing    | pytest, pytest-flask                         |

The project deliberately has no ORM, no frontend framework, and no build step.

---

## Project Structure

```
Expense_Tracker/
├── app.py                  # Flask app and all routes (single file, no blueprints)
├── database/
│   ├── __init__.py
│   └── db.py               # SQLite helpers: get_db(), init_db(), seed_db()
├── templates/
│   ├── base.html           # Shared layout; every page extends this
│   ├── landing.html        # Home page
│   ├── register.html
│   ├── login.html
│   ├── terms.html
│   └── privacy.html
├── static/
│   ├── css/
│   │   ├── style.css       # Global styles
│   │   └── landing.css     # Landing-page-only styles
│   └── js/
│       └── main.js         # Vanilla JS
├── tests/
│   └── test_db.py          # Data-layer tests
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

The demo user comes with eight sample expenses, one or more in each category, dated within the current month. Login is not wired up yet, so the account can't be used in the UI until the authentication step lands.

---

## Configuration

| Setting       | Value                              | Where                |
| ------------- | ---------------------------------- | -------------------- |
| Port          | `5001`                             | `app.py`             |
| Debug mode    | Enabled                            | `app.py`             |
| Database file | `expense_tracker.db` (project root) | `database/db.py` (`DB_PATH`) |

> **Note:** `python app.py` starts Flask's development server in debug mode. Don't expose it to the internet. For a real deployment, run the app under a production WSGI server such as Gunicorn or Waitress, turn debug mode off, and set a strong `SECRET_KEY` once sessions are added.

---

## Database

The schema is created by `init_db()`. It is safe to run repeatedly, because every table uses `CREATE TABLE IF NOT EXISTS`.

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

| Function    | Purpose                                                                                     |
| ----------- | ------------------------------------------------------------------------------------------- |
| `get_db()`  | Returns a connection with `sqlite3.Row` access and foreign keys on. The caller must close it. |
| `init_db()` | Creates all tables.                                                                         |
| `seed_db()` | Inserts the demo user and sample expenses, but only if the `users` table is empty.          |

### Resetting the database

Stop the app, delete `expense_tracker.db`, and start the app again. A fresh database is created and seeded.

---

## Routes

| Method | Path                    | Description             | Status      |
| ------ | ----------------------- | ----------------------- | ----------- |
| GET    | `/`                     | Landing page            | Done        |
| GET    | `/register`             | Registration page       | UI only     |
| GET    | `/login`                | Login page              | UI only     |
| GET    | `/terms`                | Terms and Conditions    | Done        |
| GET    | `/privacy`              | Privacy Policy          | Done        |
| GET    | `/logout`               | Log out                 | Placeholder |
| GET    | `/profile`              | User profile            | Placeholder |
| GET    | `/expenses/add`         | Add an expense          | Placeholder |
| GET    | `/expenses/<id>/edit`   | Edit an expense         | Placeholder |
| GET    | `/expenses/<id>/delete` | Delete an expense       | Placeholder |

---

## Running Tests

```bash
python -m pytest
```

Tests run against a temporary database (the `db_path` fixture patches `DB_PATH`), so your local `expense_tracker.db` is never touched. The suite covers:

- Connection settings (row factory and foreign keys)
- Table creation and the exact column layout, including repeated `init_db()` calls
- Seeding that runs only once, with valid categories and dates
- Password hashing for the demo user

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

## Roadmap

- [x] **Step 1:** Database setup (schema, connection helper, seed data)
- [x] Landing, Terms, and Privacy pages
- [ ] **Step 2:** User registration
- [ ] **Step 3:** Login and logout
- [ ] **Step 4:** Profile page
- [ ] **Steps 5–6:** Expense dashboard and summaries
- [ ] **Step 7:** Add expense
- [ ] **Step 8:** Edit expense
- [ ] **Step 9:** Delete expense

---

## Contributing

1. Fork the repository and create a feature branch:
   ```bash
   git checkout -b feature/your-feature
   ```
2. Follow the [Development Guidelines](#development-guidelines).
3. Add or update tests, and make sure `python -m pytest` passes.
4. Write commit messages in the form `area: short description`, for example `landing: add terms and privacy links to footer`.
5. Open a pull request against `main`.
