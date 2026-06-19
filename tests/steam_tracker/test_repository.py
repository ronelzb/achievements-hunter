import uuid

import pytest

import steam_tracker.db as db_module
from steam_tracker.db import GuideText, Strategy
from steam_tracker.repository import (
    get_latest_guide,
    get_latest_strategy,
    save_guide,
    save_strategy,
)


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_SessionLocal", None)
    db_module.init_db()


# ── GuideText ─────────────────────────────────────────────────────────────────


def test_save_guide_returns_row_with_uuid_id():
    with db_module.get_session() as session:
        row = save_guide(
            session, app_id=1, source="http://example.com", raw_text="guide"
        )
        assert row.id is not None
        assert isinstance(row.id, uuid.UUID)
        assert row.app_id == 1
        assert row.source == "http://example.com"
        assert row.raw_text == "guide"


def test_save_guide_starts_version_at_1():
    with db_module.get_session() as session:
        row = save_guide(session, app_id=1, source="u", raw_text="t")
        assert row.version == 1


def test_save_guide_increments_version_per_app_id():
    with db_module.get_session() as session:
        r1 = save_guide(session, app_id=10, source="u1", raw_text="first")
        r2 = save_guide(session, app_id=10, source="u2", raw_text="second")
        r3 = save_guide(session, app_id=10, source="u3", raw_text="third")
        assert r1.version == 1
        assert r2.version == 2
        assert r3.version == 3


def test_save_guide_versions_are_independent_per_app_id():
    with db_module.get_session() as session:
        a = save_guide(session, app_id=1, source="u", raw_text="a")
        b = save_guide(session, app_id=2, source="u", raw_text="b")
        assert a.version == 1
        assert b.version == 1


def test_save_guide_created_at_is_set():
    with db_module.get_session() as session:
        row = save_guide(session, app_id=1, source="u", raw_text="t")
        assert row.created_at is not None


def test_save_guide_deleted_defaults_to_false():
    with db_module.get_session() as session:
        row = save_guide(session, app_id=1, source="u", raw_text="t")
        assert row.deleted is False


def test_get_latest_guide_returns_none_when_empty():
    with db_module.get_session() as session:
        assert get_latest_guide(session, app_id=999) is None


def test_get_latest_guide_returns_highest_version():
    with db_module.get_session() as session:
        save_guide(session, app_id=10, source="u1", raw_text="first")
        save_guide(session, app_id=10, source="u2", raw_text="second")
        row = get_latest_guide(session, app_id=10)
        assert row is not None
        assert row.version == 2
        assert row.raw_text == "second"


def test_get_latest_guide_ignores_other_app_ids():
    with db_module.get_session() as session:
        save_guide(session, app_id=1, source="u1", raw_text="game1")
        save_guide(session, app_id=2, source="u2", raw_text="game2")
        row = get_latest_guide(session, app_id=1)
        assert row is not None
        assert row.raw_text == "game1"


def test_get_latest_guide_excludes_deleted_rows():
    with db_module.get_session() as session:
        row = save_guide(session, app_id=5, source="u", raw_text="deleted")
        row.deleted = True
        session.commit()
        assert get_latest_guide(session, app_id=5) is None


def test_multiple_guide_rows_accumulate():
    with db_module.get_session() as session:
        for i in range(3):
            save_guide(session, app_id=42, source=f"url{i}", raw_text=f"text{i}")
        assert session.query(GuideText).filter_by(app_id=42).count() == 3


# ── Strategy ──────────────────────────────────────────────────────────────────


def test_save_strategy_returns_row_with_uuid_id():
    with db_module.get_session() as session:
        guide = save_guide(session, app_id=1, source="u", raw_text="t")
        payload = {"summary": "test", "sections": []}
        row = save_strategy(
            session,
            app_id=1,
            guide_text=guide,
            model="claude-sonnet-4-6",
            strategy_json=payload,
        )
        assert row.id is not None
        assert isinstance(row.id, uuid.UUID)
        assert row.app_id == 1
        assert row.guide_text_id == guide.id
        assert row.model == "claude-sonnet-4-6"
        assert row.strategy_json == payload


def test_save_strategy_starts_version_at_1():
    with db_module.get_session() as session:
        guide = save_guide(session, app_id=1, source="u", raw_text="t")
        row = save_strategy(
            session, app_id=1, guide_text=guide, model="m", strategy_json={}
        )
        assert row.version == 1


def test_save_strategy_increments_version_per_app_id():
    with db_module.get_session() as session:
        guide = save_guide(session, app_id=20, source="u", raw_text="t")
        r1 = save_strategy(
            session, app_id=20, guide_text=guide, model="m", strategy_json={"v": 1}
        )
        r2 = save_strategy(
            session, app_id=20, guide_text=guide, model="m", strategy_json={"v": 2}
        )
        assert r1.version == 1
        assert r2.version == 2


def test_save_strategy_rejects_mismatched_app_id():
    with db_module.get_session() as session:
        guide = save_guide(session, app_id=1, source="u", raw_text="t")
        with pytest.raises(ValueError, match="does not match app_id"):
            save_strategy(
                session, app_id=99, guide_text=guide, model="m", strategy_json={}
            )


def test_save_strategy_deleted_defaults_to_false():
    with db_module.get_session() as session:
        guide = save_guide(session, app_id=1, source="u", raw_text="t")
        row = save_strategy(
            session, app_id=1, guide_text=guide, model="m", strategy_json={}
        )
        assert row.deleted is False


def test_get_latest_strategy_returns_none_when_empty():
    with db_module.get_session() as session:
        assert get_latest_strategy(session, app_id=999) is None


def test_get_latest_strategy_returns_highest_version():
    with db_module.get_session() as session:
        guide = save_guide(session, app_id=20, source="u", raw_text="t")
        save_strategy(
            session, app_id=20, guide_text=guide, model="m", strategy_json={"v": 1}
        )
        save_strategy(
            session, app_id=20, guide_text=guide, model="m", strategy_json={"v": 2}
        )
        row = get_latest_strategy(session, app_id=20)
        assert row is not None
        assert row.version == 2
        assert row.strategy_json == {"v": 2}


def test_get_latest_strategy_ignores_other_app_ids():
    with db_module.get_session() as session:
        g1 = save_guide(session, app_id=1, source="u", raw_text="t")
        g2 = save_guide(session, app_id=2, source="u", raw_text="t")
        save_strategy(
            session, app_id=1, guide_text=g1, model="m", strategy_json={"app": 1}
        )
        save_strategy(
            session, app_id=2, guide_text=g2, model="m", strategy_json={"app": 2}
        )
        row = get_latest_strategy(session, app_id=2)
        assert row is not None
        assert row.strategy_json == {"app": 2}


def test_get_latest_strategy_excludes_deleted_rows():
    with db_module.get_session() as session:
        guide = save_guide(session, app_id=7, source="u", raw_text="t")
        row = save_strategy(
            session, app_id=7, guide_text=guide, model="m", strategy_json={}
        )
        row.deleted = True
        session.commit()
        assert get_latest_strategy(session, app_id=7) is None


def test_multiple_strategy_rows_accumulate():
    with db_module.get_session() as session:
        guide = save_guide(session, app_id=42, source="u", raw_text="t")
        for i in range(3):
            save_strategy(
                session,
                app_id=42,
                guide_text=guide,
                model="m",
                strategy_json={"run": i},
            )
        assert session.query(Strategy).filter_by(app_id=42).count() == 3


# ── guide_text_id FK consistency ─────────────────────────────────────────────


def test_strategy_guide_text_id_matches_guide():
    with db_module.get_session() as session:
        guide = save_guide(session, app_id=1, source="u", raw_text="t")
        strategy = save_strategy(
            session, app_id=1, guide_text=guide, model="m", strategy_json={}
        )
        assert strategy.guide_text_id == guide.id


def test_refine_reuses_same_guide_text_id():
    with db_module.get_session() as session:
        guide = save_guide(session, app_id=1, source="u", raw_text="t")
        s1 = save_strategy(
            session, app_id=1, guide_text=guide, model="m", strategy_json={"v": 1}
        )
        s2 = save_strategy(
            session, app_id=1, guide_text=guide, model="m", strategy_json={"v": 2}
        )
        assert s1.guide_text_id == s2.guide_text_id == guide.id
        assert s2.version == s1.version + 1
