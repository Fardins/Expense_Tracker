import os
import sqlite3
from datetime import date

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "expense_tracker.db")

CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    amount      REAL NOT NULL,
    category    TEXT NOT NULL,
    date        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
"""


def get_db():
    """Return a SQLite connection with Row access and foreign keys enabled.

    The caller is responsible for closing the connection.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables. Safe to call multiple times."""
    conn = get_db()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def seed_db():
    """Insert a demo user and sample expenses, only if no users exist yet."""
    conn = get_db()
    try:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return

        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        user_id = cur.lastrowid

        today = date.today()

        def day_in_month(day):
            # Clamp to today so seed dates are valid and never in the future.
            return today.replace(day=min(day, today.day)).isoformat()

        sample_expenses = [
            (12.50, "Food", 1, "Lunch"),
            (3.75, "Transport", 3, "Bus fare"),
            (85.00, "Bills", 6, "Electricity bill"),
            (20.00, "Health", 9, "Pharmacy"),
            (15.99, "Entertainment", 12, "Movie ticket"),
            (45.30, "Shopping", 15, "New shoes"),
            (7.25, "Other", 20, "Miscellaneous"),
            (32.40, "Food", 25, "Groceries"),
        ]
        rows = [
            (user_id, amount, category, day_in_month(day), description)
            for amount, category, day, description in sample_expenses
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def get_user_by_email(email):
    """Return the users row for ``email`` as a sqlite3.Row, or None."""
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    finally:
        conn.close()


def create_user(name, email, password):
    """Insert a new user with a hashed password and return its id.

    Raises sqlite3.IntegrityError if the email is already registered.
    """
    password_hash = generate_password_hash(password)
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def create_expense(user_id, amount, category, date, description=None):
    """Insert one expense for ``user_id`` and return its id."""
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_expense_by_id(expense_id, user_id):
    """Return (id, amount, category, date, description) if the expense belongs
    to ``user_id``, else None. Ownership is enforced in the WHERE clause.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
    finally:
        conn.close()


def update_expense(expense_id, user_id, amount, category, date, description=None):
    """Update one expense owned by ``user_id``. Return True if a row matched.

    Never touches ``user_id`` or ``created_at``.
    """
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? "
            "WHERE id = ? AND user_id = ?",
            (amount, category, date, description, expense_id, user_id),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def delete_expense_row(expense_id, user_id):
    """Delete one expense owned by ``user_id``. Return True if a row was deleted."""
    conn = get_db()
    try:
        cur = conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def get_user_by_id(user_id):
    """Return id, name, email, created_at for ``user_id``, or None.

    Deliberately excludes password_hash so it can never reach a template.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


def get_recent_expenses(user_id, limit=10, *, date_from=None, date_to=None):
    """Return rows (date, description, category, amount, id), newest first.

    ``date_from`` / ``date_to`` are inclusive 'YYYY-MM-DD' bounds; None = no bound.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT date, description, category, amount, id FROM expenses "
            "WHERE user_id = ? "
            "AND (? IS NULL OR date >= ?) AND (? IS NULL OR date <= ?) "
            "ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, date_from, date_from, date_to, date_to, limit),
        ).fetchall()
    finally:
        conn.close()


def get_expense_summary(user_id, *, date_from=None, date_to=None):
    """Return {'total': float, 'count': int} from one SUM/COUNT query.

    ``date_from`` / ``date_to`` are inclusive 'YYYY-MM-DD' bounds; None = no bound.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
            "FROM expenses WHERE user_id = ? "
            "AND (? IS NULL OR date >= ?) AND (? IS NULL OR date <= ?)",
            (user_id, date_from, date_from, date_to, date_to),
        ).fetchone()
        return {"total": float(row["total"]), "count": int(row["count"])}
    finally:
        conn.close()


def get_category_totals(user_id, *, date_from=None, date_to=None):
    """Return rows (category, amount), ordered by amount DESC, category ASC.

    ``date_from`` / ``date_to`` are inclusive 'YYYY-MM-DD' bounds; None = no bound.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT category, SUM(amount) AS amount FROM expenses "
            "WHERE user_id = ? "
            "AND (? IS NULL OR date >= ?) AND (? IS NULL OR date <= ?) "
            "GROUP BY category "
            "ORDER BY amount DESC, category ASC",
            (user_id, date_from, date_from, date_to, date_to),
        ).fetchall()
    finally:
        conn.close()
