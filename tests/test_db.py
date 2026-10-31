import re
import sqlite3
from contextlib import closing
from datetime import date

import pytest
from werkzeug.security import check_password_hash

from database import db


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", str(path))
    return path


@pytest.fixture
def seeded(db_path):
    db.init_db()
    db.seed_db()
    return db_path


def test_get_db_row_factory(db_path):
    with closing(db.get_db()) as conn:
        assert conn.row_factory is sqlite3.Row
        assert conn.execute("SELECT 1 AS x").fetchone()["x"] == 1


def test_get_db_foreign_keys_on(db_path):
    with closing(db.get_db()) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_init_db_creates_file_and_tables_idempotently(db_path):
    db.init_db()
    db.init_db()
    assert db_path.exists()

    with closing(db.get_db()) as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"users", "expenses"} <= tables

        user_cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)")]
        assert user_cols == ["id", "name", "email", "password_hash", "created_at"]

        expense_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(expenses)")
        ]
        assert expense_cols == [
            "id", "user_id", "amount", "category", "date", "description", "created_at",
        ]


def test_seed_inserts_only_once(seeded):
    db.seed_db()
    with closing(db.get_db()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 8


def test_seed_expenses_categories_and_dates(seeded):
    today = date.today()
    with closing(db.get_db()) as conn:
        user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        rows = conn.execute("SELECT * FROM expenses").fetchall()

    assert {r["category"] for r in rows} == set(db.CATEGORIES)
    for r in rows:
        assert r["user_id"] == user_id
        assert isinstance(r["amount"], float)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date"])
        assert r["date"].startswith(today.strftime("%Y-%m"))
        assert r["date"] <= today.isoformat()


def test_demo_user_password_hashed(seeded):
    with closing(db.get_db()) as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()

    assert user["name"] == "Demo User"
    assert user["password_hash"] != "demo123"
    assert check_password_hash(user["password_hash"], "demo123")
    assert not check_password_hash(user["password_hash"], "wrong")


def test_unique_email_enforced(seeded):
    with closing(db.get_db()) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Someone", "demo@spendly.com", "x"),
            )


def test_foreign_key_enforced(seeded):
    with closing(db.get_db()) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date) "
                "VALUES (?, ?, ?, ?)",
                (9999, 10.0, "Food", date.today().isoformat()),
            )
