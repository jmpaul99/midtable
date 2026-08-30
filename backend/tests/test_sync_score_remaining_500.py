"""Regression: remaining opaque HTTP 500 after #22 baselines savepoint.

Run #348 (2026-08-30 16:59 UTC, SHA 52e23fde = #22 merge) still failed with:
  Attempt 1/4 failed with HTTP 500
  {"detail":"Internal server error"}
Same shape as #343/#344. #23 (goals/gap-fill) does not address opaque 500s.

These guards ensure escapes become structured failures (→ HTTP 502) and that
SyncStatus create races cannot poison the outer transaction.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, String, UniqueConstraint, create_engine
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.routers import internal as internal_mod
from app.services import sync as sync_mod


class Base(DeclarativeBase):
    pass


class SyncLockRow(Base):
    __tablename__ = "sync_lock_rows"
    __table_args__ = (UniqueConstraint("provider", "code", "year"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    code: Mapped[str] = mapped_column(String(16))
    year: Mapped[int] = mapped_column(Integer)


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


def test_swallowed_sync_status_create_integrity_error_poisons_commit(memory_db: Session):
    """Document pre-fix mode: create race without savepoint → PendingRollbackError."""
    db = memory_db
    db.add(SyncLockRow(provider="football-data.org", code="PL", year=2026))
    db.commit()
    db.add(SyncLockRow(provider="x", code="WC", year=2026))
    db.flush()
    try:
        db.add(SyncLockRow(provider="football-data.org", code="PL", year=2026))
        db.flush()
    except IntegrityError:
        pass
    with pytest.raises(PendingRollbackError):
        db.commit()


def test_savepoint_contains_sync_status_create_integrity_error(memory_db: Session):
    db = memory_db
    db.add(SyncLockRow(provider="football-data.org", code="PL", year=2026))
    db.commit()
    db.add(SyncLockRow(provider="x", code="WC", year=2026))
    db.flush()
    try:
        with db.begin_nested():
            db.add(SyncLockRow(provider="football-data.org", code="PL", year=2026))
            db.flush()
    except IntegrityError:
        pass
    db.commit()
    rows = list(db.query(SyncLockRow).all())
    assert {(r.provider, r.code, r.year) for r in rows} == {
        ("football-data.org", "PL", 2026),
        ("x", "WC", 2026),
    }


def test_ensure_sync_status_uses_savepoint_on_create(monkeypatch):
    nested_calls: list[str] = []

    @contextmanager
    def fake_nested():
        nested_calls.append("enter")
        yield
        nested_calls.append("exit")

    db = MagicMock()
    db.begin_nested.side_effect = lambda: fake_nested()
    empty = MagicMock()
    empty.first.return_value = None
    created = MagicMock()
    created.one.return_value = SimpleNamespace(id=1)
    db.scalars.side_effect = [empty, created]

    status = sync_mod._ensure_sync_status(
        db,
        provider="football-data.org",
        competition_code="PL",
        season_year=2026,
    )
    assert status.id == 1
    assert db.begin_nested.called
    assert "enter" in nested_calls


def test_sync_all_converts_unhandled_escape_to_failures_payload(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("simulated escape after #22")

    monkeypatch.setattr(sync_mod, "_sync_all_active_competitions_then_score_body", boom)
    db = MagicMock()
    payload = sync_mod.sync_all_active_competitions_then_score(db, MagicMock(), [])
    assert payload["ok"] is False
    assert payload["failures"] == 1
    assert payload["error_type"] == "RuntimeError"
    assert "simulated escape" in payload["error"]
    assert db.rollback.called


def test_sync_and_score_endpoint_returns_structured_502_on_unhandled(monkeypatch):
    def boom(*_a, **_k):
        raise MemoryError("simulated OOM-class escape")

    # Patch the name bound in the router module (from-import).
    monkeypatch.setattr(internal_mod, "sync_all_active_competitions_then_score", boom)

    app = FastAPI()
    app.include_router(internal_mod.router)

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[internal_mod.get_db] = fake_db
    app.dependency_overrides[internal_mod.get_football_provider] = lambda: MagicMock()
    from app.deps import require_cron_secret

    app.dependency_overrides[require_cron_secret] = lambda: None

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/internal/sync-and-score")
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["ok"] is False
    assert detail["failures"] == 1
    assert detail["error_type"] == "MemoryError"
    assert "simulated OOM" in detail["error"]
    # Must not be the opaque FastAPI 500 body.
    assert detail != "Internal server error"


def test_sync_and_score_endpoint_preserves_soft_failure_502(monkeypatch):
    soft = {
        "ok": False,
        "failures": 1,
        "competitions": [{"ok": False, "error": "provider down"}],
        "leagues": [],
    }
    monkeypatch.setattr(
        internal_mod,
        "sync_all_active_competitions_then_score",
        lambda *_a, **_k: soft,
    )

    app = FastAPI()
    app.include_router(internal_mod.router)

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[internal_mod.get_db] = fake_db
    app.dependency_overrides[internal_mod.get_football_provider] = lambda: MagicMock()
    from app.deps import require_cron_secret

    app.dependency_overrides[require_cron_secret] = lambda: None

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/internal/sync-and-score")
    assert response.status_code == 502
    assert response.json()["detail"]["failures"] == 1
    assert response.json()["detail"]["competitions"][0]["error"] == "provider down"


def test_sync_competition_lock_acquire_failure_returns_soft_fail(monkeypatch):
    status = SimpleNamespace(
        in_progress=False,
        in_progress_since=None,
        last_error=None,
        last_sync_at=None,
        last_summary=None,
        requests_available_minute=None,
    )
    db = MagicMock()
    db.commit.side_effect = RuntimeError("commit refused")
    monkeypatch.setattr(sync_mod, "_ensure_sync_status", lambda *_a, **_k: status)

    result = sync_mod.sync_competition_fixtures(
        db,
        MagicMock(),
        provider_key="football-data.org",
        competition_code="PL",
        season_year=2026,
    )
    assert result["ok"] is False
    assert result["status_code"] == 500
    assert "lock acquire failed" in result["error"]
