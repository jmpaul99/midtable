"""Regression: refreshing standings snapshot rows must flush deletes first.

Actions Sync and score #349/#350 (SHA e4e61f5, post-#26 deploy) failed with HTTP 502:
  PendingRollbackError wrapping UniqueViolation on
  standings_snapshot_rows_snapshot_team_key (snapshot_id, team_id)=(41, 7)

Root cause: build_snapshot_for_kickoff deleted existing rows then inserted the
same (snapshot_id, team_id) keys in one flush. Without an intervening flush,
Postgres still saw the old rows → UniqueViolation → poisoned session.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Integer, UniqueConstraint, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.services import standings as standings_mod
from app.services.scoring import RankedTeam


class Base(DeclarativeBase):
    pass


class SnapshotRow(Base):
    __tablename__ = "snapshot_rows_refresh"
    __table_args__ = (UniqueConstraint("snapshot_id", "team_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(Integer)
    team_id: Mapped[int] = mapped_column(Integer)


@pytest.fixture()
def memory_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_delete_then_insert_same_key_without_flush_raises(memory_db: Session):
    """Document the failure mode that poisoned sync-and-score (#349/#350)."""
    db = memory_db
    db.add(SnapshotRow(snapshot_id=41, team_id=7))
    db.commit()

    existing = db.query(SnapshotRow).filter_by(snapshot_id=41, team_id=7).one()
    db.delete(existing)
    # No flush — same unique key inserted in the same unit of work.
    db.add(SnapshotRow(snapshot_id=41, team_id=7))
    with pytest.raises(IntegrityError):
        db.flush()


def test_delete_flush_then_insert_same_key_succeeds(memory_db: Session):
    """Pattern used by _replace_snapshot_rows / fixed build_snapshot_for_kickoff."""
    db = memory_db
    db.add(SnapshotRow(snapshot_id=41, team_id=7))
    db.commit()

    existing = db.query(SnapshotRow).filter_by(snapshot_id=41, team_id=7).one()
    db.delete(existing)
    db.flush()
    db.add(SnapshotRow(snapshot_id=41, team_id=7))
    db.flush()
    db.commit()
    rows = list(db.query(SnapshotRow).filter_by(snapshot_id=41, team_id=7).all())
    assert len(rows) == 1


def test_build_snapshot_for_kickoff_uses_replace_rows(monkeypatch):
    """Ensure refresh path goes through _replace_snapshot_rows (flush-after-delete)."""
    kickoff = datetime(2026, 8, 30, 15, 0, tzinfo=UTC)
    existing = SimpleNamespace(
        id=41,
        rows=[],
        stale=True,
        computed_at=None,
    )
    replace_calls: list[tuple] = []

    def fake_replace(db, snapshot, rows):
        replace_calls.append((snapshot, tuple(rows)))

    monkeypatch.setattr(standings_mod, "matches_for_competition", lambda *a, **k: [])
    monkeypatch.setattr(standings_mod, "initial_rows_for_competition", lambda *a, **k: [])
    monkeypatch.setattr(
        standings_mod,
        "build_standings_before_kickoff",
        lambda **k: (
            RankedTeam(
                team_id=7,
                rank=1,
                played=1,
                points=3,
                goals_for=2,
                goals_against=0,
                goal_difference=2,
            ),
        ),
    )
    monkeypatch.setattr(standings_mod, "_replace_snapshot_rows", fake_replace)

    db = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = existing
    db.scalars.return_value = scalars

    @contextmanager
    def unused_nested():
        raise AssertionError("should not create snapshot when existing")
        yield  # pragma: no cover

    db.begin_nested.side_effect = unused_nested

    out = standings_mod.build_snapshot_for_kickoff(
        db,
        provider="football-data.org",
        competition_code="PL",
        season_year=2025,
        kickoff_at=kickoff,
        pool_id=1,
        mark_fresh=True,
    )
    assert out is existing
    assert existing.stale is False
    assert len(replace_calls) == 1
    assert replace_calls[0][0] is existing
    assert replace_calls[0][1] == ((7, 1, 1, 3, 2, 0, 2),)
