"""Regression: baselines DB errors must not poison /internal/sync-and-score.

Before the fix, ensure_competition_season_table_baselines failures were caught
without a savepoint. On PostgreSQL/SQLite, a flush IntegrityError aborts the
transaction; the next db.commit() raised PendingRollbackError, which escaped
sync_all_active_competitions_then_score and became HTTP 500
{"detail":"Internal server error"} after a long sync (~60s+) — matching the
2026-08-29 Sync and score failures (runs 33266902529, 33275822927).
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Integer, String, create_engine
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.services import sync as sync_mod


class Base(DeclarativeBase):
    pass


class UniqueRow(Base):
    __tablename__ = "unique_rows"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)


@pytest.fixture()
def memory_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    db.add(UniqueRow(name="seed"))
    db.commit()
    try:
        yield db
    finally:
        db.close()


def test_swallowed_flush_integrity_error_poisons_commit(memory_db: Session):
    """Document the pre-fix failure mode (no savepoint)."""
    db = memory_db
    db.add(UniqueRow(name="fixture-sync-work"))
    db.flush()
    try:
        db.add(UniqueRow(name="seed"))  # duplicate
        db.flush()
    except IntegrityError:
        pass  # old baselines handler: log and continue
    with pytest.raises(PendingRollbackError):
        db.commit()


def test_savepoint_contains_baselines_integrity_error(memory_db: Session):
    """begin_nested isolates baselines failure so outer commit succeeds."""
    db = memory_db
    db.add(UniqueRow(name="fixture-sync-work"))
    db.flush()
    try:
        with db.begin_nested():
            db.add(UniqueRow(name="seed"))
            db.flush()
    except IntegrityError:
        pass
    db.commit()
    names = {r.name for r in db.query(UniqueRow).all()}
    assert "fixture-sync-work" in names
    assert names == {"seed", "fixture-sync-work"}


def test_sync_competition_uses_savepoint_around_baselines(monkeypatch):
    """sync_competition_fixtures must wrap baselines in begin_nested."""
    nested_calls: list[str] = []

    @contextmanager
    def fake_nested():
        nested_calls.append("enter")
        yield
        nested_calls.append("exit")

    status = SimpleNamespace(
        in_progress=False,
        in_progress_since=None,
        last_error=None,
        last_sync_at=None,
        last_summary=None,
        requests_available_minute=None,
    )

    db = MagicMock()
    db.begin_nested.side_effect = lambda: fake_nested()

    provider = MagicMock()
    del provider.get_match
    provider.list_matches.return_value = ([], None)
    db.scalars.return_value.all.return_value = []

    def boom_baselines(*_a, **_k):
        raise IntegrityError("statement", {}, Exception("unique"))

    monkeypatch.setattr(sync_mod, "_ensure_sync_status", lambda *_a, **_k: status)
    # Patch the import site used inside sync_competition_fixtures.
    import app.services.standings as standings_mod

    monkeypatch.setattr(
        standings_mod,
        "ensure_competition_season_table_baselines",
        boom_baselines,
    )

    result = sync_mod.sync_competition_fixtures(
        db,
        provider,
        provider_key="football-data.org",
        competition_code="PL",
        season_year=2026,
    )
    assert result["ok"] is True
    assert db.begin_nested.called
    assert "enter" in nested_calls

def test_sync_all_reloads_changed_matches_by_id(monkeypatch):
    """After competition commit, scoring must not rely on expired ORM instances."""
    league = SimpleNamespace(id=1, public_id=uuid4(), upset_rules={})
    pool = SimpleNamespace(
        id=10,
        provider="football-data.org",
        competition_code="PL",
        season_year=2026,
        scores_match_results=True,
    )
    match = SimpleNamespace(id=42)

    def fake_sync(db, provider, *, provider_key, competition_code, season_year):
        return {
            "ok": True,
            "created": 0,
            "updated": 1,
            "skipped_missing_teams": 0,
            "changed_matches": [match],
        }

    loaded: list[list[int]] = []

    def fake_score(db, league_arg, changed):
        loaded.append([m.id for m in changed])
        return {
            "scored": 1,
            "cascaded": 1,
            "skipped_missing_snapshot": 0,
            "gap_fill_seeds": 0,
            "seed_count": 1,
        }

    db = MagicMock()
    scalars_out = MagicMock()
    scalars_out.all.return_value = [match]
    db.scalars.return_value = scalars_out

    monkeypatch.setattr(sync_mod, "sync_competition_fixtures", fake_sync)
    monkeypatch.setattr(sync_mod, "scoring_pools_for_league", lambda *_a, **_k: [pool])
    monkeypatch.setattr(sync_mod, "score_league_after_sync", fake_score)
    monkeypatch.setattr(
        sync_mod,
        "record_cron_league_result",
        lambda *_a, **_k: SimpleNamespace(public_id=uuid4()),
    )

    payload = sync_mod.sync_all_active_competitions_then_score(db, MagicMock(), [league])
    assert payload["ok"] is True
    assert loaded == [[42]]
    # Reloaded via Match.id.in_(...)
    assert db.scalars.called
