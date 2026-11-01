import importlib

import pytest

from database import db


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Flask app wired to a fresh temp database (pytest-flask adds `client`)."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    # Import lazily, after patching: importing app runs init_db/seed_db.
    # Never `import app` at module level in a test file.
    flask_app = importlib.import_module("app").app
    flask_app.config.update(TESTING=True)
    db.init_db()  # module is cached after first import; init each fresh DB
    db.seed_db()
    return flask_app
