import pytest

import steam_tracker.db as db_module


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionLocal", None)
    db_module.init_db()


# ── _resolve_db_url ───────────────────────────────────────────────────────────


def test_resolve_db_url_memory_passthrough():
    assert db_module._resolve_db_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_resolve_db_url_absolute_passthrough(tmp_path):
    abs_url = f"sqlite:///{tmp_path}/mydb.sqlite"
    assert db_module._resolve_db_url(abs_url) == abs_url


def test_resolve_db_url_non_sqlite_passthrough():
    url = "postgresql://user:pass@localhost/dbname"
    assert db_module._resolve_db_url(url) == url


def test_resolve_db_url_relative_anchors_to_project_root():
    result = db_module._resolve_db_url("sqlite:///data/platinum.db")
    assert result.startswith("sqlite:///")
    assert "data/platinum.db" in result.replace("\\", "/")
    assert "achievements-hunter" in result.replace("\\", "/")


# ── engine / session ──────────────────────────────────────────────────────────


def test_get_engine_returns_same_instance():
    e1 = db_module.get_engine()
    e2 = db_module.get_engine()
    assert e1 is e2


def test_get_session_returns_session():
    from sqlalchemy.orm import Session

    with db_module.get_session() as session:
        assert isinstance(session, Session)


def test_init_db_creates_tables():
    engine = db_module.get_engine()
    from sqlalchemy import inspect

    tables = inspect(engine).get_table_names()
    assert "guide_text" in tables
    assert "strategy" in tables
