from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import GuideText, Strategy


def _next_version(session: Session, model: type, app_id: int) -> int:
    current = session.query(func.max(model.version)).filter_by(app_id=app_id).scalar()
    return (current or 0) + 1


def get_latest_guide(session: Session, app_id: int) -> GuideText | None:
    return (
        session.query(GuideText)
        .filter_by(app_id=app_id, deleted=False)
        .order_by(GuideText.version.desc())
        .first()
    )


def save_guide(session: Session, app_id: int, source: str, raw_text: str) -> GuideText:
    row = GuideText(
        app_id=app_id,
        version=_next_version(session, GuideText, app_id),
        source=source,
        raw_text=raw_text,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_latest_strategy(session: Session, app_id: int) -> Strategy | None:
    return (
        session.query(Strategy)
        .filter_by(app_id=app_id, deleted=False)
        .order_by(Strategy.version.desc())
        .first()
    )


def save_strategy(
    session: Session,
    app_id: int,
    guide_text: GuideText,
    model: str,
    strategy_json: dict,
) -> Strategy:
    if guide_text.app_id != app_id:
        raise ValueError(
            f"guide_text.app_id {guide_text.app_id} does not match app_id {app_id}"
        )
    row = Strategy(
        app_id=app_id,
        version=_next_version(session, Strategy, app_id),
        guide_text_id=guide_text.id,
        model=model,
        strategy_json=strategy_json,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
