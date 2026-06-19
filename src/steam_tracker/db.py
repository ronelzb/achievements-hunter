from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import uuid_utils
from sqlalchemy import (
    INTEGER,
    JSON,
    SMALLINT,
    TEXT,
    TIMESTAMP,
    ForeignKey,
    UniqueConstraint,
    Uuid,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .settings import DATABASE_URL

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_db_url(url: str) -> str:
    """Anchor a relative sqlite:/// path to the project root; leave all other URLs unchanged."""
    if url.startswith("sqlite:///"):
        path_str = url[len("sqlite:///") :]
        if path_str == ":memory:" or Path(path_str).is_absolute():
            return url
        path = (_PROJECT_ROOT / path_str).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    return url


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        url = _resolve_db_url(DATABASE_URL)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, echo=False)
    return _engine


def init_db() -> None:
    """Create all tables. Safe to call multiple times (CREATE TABLE IF NOT EXISTS)."""
    Base.metadata.create_all(bind=get_engine())


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autocommit=False, autoflush=False
        )
    return _SessionLocal()


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


def _new_id() -> uuid_utils.UUID:
    return uuid_utils.uuid7()


class Base(DeclarativeBase):
    id: Mapped[uuid_utils.UUID] = mapped_column(
        Uuid(), primary_key=True, default=_new_id
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=lambda: datetime.now(UTC)
    )
    modified_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    deleted: Mapped[bool] = mapped_column(default=False)


class GuideText(Base):
    __tablename__ = "guide_text"
    __table_args__ = (
        UniqueConstraint("app_id", "version"),
        UniqueConstraint("app_id", "content_hash"),
    )

    app_id: Mapped[int] = mapped_column(INTEGER)
    version: Mapped[int] = mapped_column(SMALLINT)
    source: Mapped[str] = mapped_column(TEXT)
    raw_text: Mapped[str] = mapped_column(TEXT)
    content_hash: Mapped[str] = mapped_column(TEXT, index=True)


class Strategy(Base):
    __tablename__ = "strategy"
    __table_args__ = (UniqueConstraint("app_id", "version"),)

    app_id: Mapped[int] = mapped_column(INTEGER)
    version: Mapped[int] = mapped_column(SMALLINT)
    guide_text_id: Mapped[uuid_utils.UUID | None] = mapped_column(
        Uuid(), ForeignKey("guide_text.id"), index=True, nullable=True
    )
    model: Mapped[str] = mapped_column(TEXT)
    strategy_json: Mapped[dict] = mapped_column(JSON)
