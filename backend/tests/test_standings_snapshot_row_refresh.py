"""Regression: standings snapshot row replace must survive same-session refresh.

#27 fixed delete-without-flush in build_snapshot_for_kickoff by routing through
``_replace_snapshot_rows``. Sync and score #380 (SHA d086ae3, post-#27) still
failed intermittently with UniqueViolation on
``standings_snapshot_rows_snapshot_team_key`` for keys like (54,7)/(56,7)/…

Root cause (#380): ``_replace_snapshot_rows`` deleted via the ORM relationship
collection, then inserted with ``db.add(... snapshot_id=...)`` only. After the
first replace in a Session, delete-orphan leaves deleted "zombie" instances in
``snapshot.rows`` while the new rows are not attached to the collection. A
second replace (another seed / shared kickoff) issues ``DELETE WHERE id=<stale
pk>`` which is a no-op on Postgres (identities not reused). The following
INSERT collides with the live row → UniqueViolation → poisoned session → 502.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import (
    ForeignKey,
    Integer,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.orm.attributes import instance_state

from app.services import standings as standings_mod
from app.services.scoring import RankedTeam


class Base(DeclarativeBase):
    pass


class SnapshotRow(Base):
    """Minimal unique-key table for the flush-ordering docs tests."""

    __tablename__ = "snapshot_rows_refresh"
    __table_args__ = (UniqueConstraint("snapshot_id", "team_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(Integer)
    team_id: Mapped[int] = mapped_column(Integer)


class Snap(Base):
    """Mirrors StandingsSnapshot.rows cascade used in production."""

    __tablename__ = "snaps_replace"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rows: Mapped[list["SnapRow"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )


class SnapRow(Base):
    __tablename__ = "snap_rows_replace"
    __table_args__ = (UniqueConstraint("snapshot_id", "team_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("snaps_replace.id", ondelete="CASCADE")
    )
    team_id: Mapped[int] = mapped_column(Integer)
    rank: Mapped[int] = mapped_column(Integer, default=1)
    played: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    goals_for: Mapped[int] = mapped_column(Integer, default=0)
    goals_against: Mapped[int] = mapped_column(Integer, default=0)
    goal_difference: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped["Snap"] = relationship(back_populates="rows")


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


@pytest.fixture()
def pg_like_db() -> Session:
    """SQLite with AUTOINCREMENT so deleted PKs are not reused (Postgres-like)."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE snaps_replace (id INTEGER PRIMARY KEY AUTOINCREMENT)"))
        conn.execute(
            text(
                """
                CREATE TABLE snap_rows_replace (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    team_id INTEGER NOT NULL,
                    rank INTEGER NOT NULL DEFAULT 1,
                    played INTEGER NOT NULL DEFAULT 0,
                    points INTEGER NOT NULL DEFAULT 0,
                    goals_for INTEGER NOT NULL DEFAULT 0,
                    goals_against INTEGER NOT NULL DEFAULT 0,
                    goal_difference INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (snapshot_id, team_id),
                    FOREIGN KEY(snapshot_id) REFERENCES snaps_replace (id) ON DELETE CASCADE
                )
                """
            )
        )
        # Keep metadata tables that create_all would add for SnapshotRow unused here.
        Base.metadata.create_all(
            conn,
            tables=[SnapshotRow.__table__],
            checkfirst=True,
        )
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
    """Flush-after-delete alone is necessary but not sufficient for #380."""
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


def _old_replace_via_collection(db: Session, snapshot: Snap, rows: list[tuple]) -> None:
    """Pre-fix pattern: ORM delete from collection + FK-only insert (#27 / #380)."""
    for row in list(snapshot.rows):
        db.delete(row)
    db.flush()
    for team_id, rank, played, points, gf, ga, gd in rows:
        db.add(
            SnapRow(
                snapshot_id=snapshot.id,
                team_id=team_id,
                rank=rank,
                played=played,
                points=points,
                goals_for=gf,
                goals_against=ga,
                goal_difference=gd,
            )
        )
    db.flush()


def test_old_collection_replace_unique_violates_on_second_call(pg_like_db: Session):
    """#380: second same-session replace UniqueViolates when PKs are not reused."""
    db = pg_like_db
    snap = Snap()
    db.add(snap)
    db.flush()
    db.add(SnapRow(snapshot_id=snap.id, team_id=7, rank=1))
    db.flush()
    db.commit()

    snap = db.get(Snap, snap.id)
    assert snap is not None
    _ = list(snap.rows)

    _old_replace_via_collection(
        db, snap, [(7, 1, 1, 3, 2, 0, 2)]
    )
    # Zombie stays in the collection; new DB row is not attached.
    assert len(snap.rows) == 1
    assert instance_state(snap.rows[0]).deleted is True
    live = db.execute(
        text("SELECT id, rank FROM snap_rows_replace WHERE snapshot_id = :sid"),
        {"sid": snap.id},
    ).fetchall()
    assert len(live) == 1
    assert live[0][0] != snap.rows[0].id  # Postgres-like: new PK

    with pytest.raises(IntegrityError):
        _old_replace_via_collection(
            db, snap, [(7, 1, 2, 6, 4, 0, 4)]
        )


def test_replace_snapshot_rows_twice_same_session(pg_like_db: Session, monkeypatch):
    """Fixed helper: SQL DELETE + expire + append survives repeated refresh."""
    monkeypatch.setattr(standings_mod, "StandingsSnapshotRow", SnapRow)
    db = pg_like_db
    snap = Snap()
    db.add(snap)
    db.flush()
    db.add(SnapRow(snapshot_id=snap.id, team_id=7, rank=1, played=0, points=0))
    db.add(
        SnapRow(
            snapshot_id=snap.id,
            team_id=8,
            rank=2,
            played=0,
            points=0,
        )
    )
    db.flush()
    db.commit()

    snap = db.get(Snap, snap.id)
    assert snap is not None
    _ = list(snap.rows)

    standings_mod._replace_snapshot_rows(
        db,
        snap,
        [
            (7, 1, 1, 3, 2, 0, 2),
            (8, 2, 1, 0, 0, 1, -1),
        ],
    )
    assert {(r.team_id, r.rank, r.points) for r in snap.rows} == {
        (7, 1, 3),
        (8, 2, 0),
    }

    # Second call — same Session, same snapshot (multi-seed / shared kickoff).
    standings_mod._replace_snapshot_rows(
        db,
        snap,
        [
            (7, 2, 2, 3, 2, 2, 0),
            (8, 1, 2, 6, 3, 0, 3),
        ],
    )
    assert {(r.team_id, r.rank, r.points) for r in snap.rows} == {
        (7, 2, 3),
        (8, 1, 6),
    }
    assert all(not instance_state(r).deleted for r in snap.rows)
    db_rows = db.execute(
        text(
            "SELECT team_id, rank, points FROM snap_rows_replace "
            "WHERE snapshot_id = :sid ORDER BY team_id"
        ),
        {"sid": snap.id},
    ).fetchall()
    assert db_rows == [(7, 2, 3), (8, 1, 6)]


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
