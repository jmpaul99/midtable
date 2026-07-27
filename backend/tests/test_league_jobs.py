"""League job enqueue/run/latest and cron persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models import LeagueJob
from app.services import league_jobs as jobs_mod
from app.services.league_jobs import (
    ActiveJobConflict,
    enqueue_league_job,
    latest_jobs_for_league,
    record_cron_league_result,
    run_league_job,
)
from app.services.sync import sync_all_active_competitions_then_score


def _job(
    *,
    league_id: int = 1,
    kind: str = "sync",
    source: str = "commissioner",
    status: str = "pending",
    public_id=None,
) -> LeagueJob:
    job = LeagueJob(
        league_id=league_id,
        kind=kind,
        source=source,
        status=status,
        created_by_profile_id=None,
    )
    job.id = 1
    job.public_id = public_id or uuid4()
    job.created_at = datetime.now(UTC)
    job.started_at = None
    job.finished_at = None
    job.error = None
    job.summary = None
    return job


def test_enqueue_raises_when_active_job_exists():
    league = SimpleNamespace(id=1, public_id=uuid4())
    existing = _job(status="running")
    db = MagicMock()
    db.scalars.return_value.first.return_value = existing

    with pytest.raises(ActiveJobConflict) as exc:
        enqueue_league_job(db, league, kind="sync", created_by_profile_id=9)
    assert exc.value.job is existing
    db.add.assert_not_called()


def test_enqueue_creates_pending_job():
    league = SimpleNamespace(id=1, public_id=uuid4())
    db = MagicMock()
    db.scalars.return_value.first.return_value = None

    def refresh(job):
        job.public_id = uuid4()
        job.created_at = datetime.now(UTC)

    db.refresh.side_effect = refresh

    job = enqueue_league_job(
        db, league, kind="recompute", created_by_profile_id=3
    )
    assert job.kind == "recompute"
    assert job.source == "commissioner"
    assert job.status == "pending"
    assert job.created_by_profile_id == 3
    db.add.assert_called_once()
    db.commit.assert_called()


def test_latest_jobs_independent_per_source():
    league_id = 7
    manual = _job(league_id=league_id, source="commissioner", kind="recompute", status="succeeded")
    cron = _job(league_id=league_id, source="cron", kind="sync", status="succeeded")

    db = MagicMock()

    def scalars(stmt):
        out = MagicMock()
        # Order: first call manual, second cron — based on source in where clause is hard;
        # instead return based on call count.
        return out

    calls: list[str] = []

    def fake_latest(db_arg, lid, source):
        calls.append(source)
        return manual if source == "commissioner" else cron

    # Patch helper used by latest_jobs_for_league
    from app.services import league_jobs as mod

    original = mod._latest_for_source
    mod._latest_for_source = fake_latest  # type: ignore[assignment]
    try:
        latest = latest_jobs_for_league(db, league_id)
    finally:
        mod._latest_for_source = original  # type: ignore[assignment]

    assert latest["manual"] is manual
    assert latest["cron"] is cron
    assert calls == ["commissioner", "cron"]


def test_record_cron_and_manual_latest_independent(monkeypatch):
    """Cron insert must not clear the notion of a separate manual latest."""
    league = SimpleNamespace(id=1, public_id=uuid4())
    db = MagicMock()

    cron_job = record_cron_league_result(
        db,
        league,
        ok=True,
        summary={"scored": 2, "cascaded": 0, "skipped_missing_snapshot": 0},
    )
    assert cron_job.source == "cron"
    assert cron_job.status == "succeeded"
    assert cron_job.summary["scored"] == 2
    db.add.assert_called()
    db.flush.assert_called()


def test_run_league_job_sync_success(monkeypatch):
    job_id = uuid4()
    job = _job(public_id=job_id, status="pending", kind="sync")
    league = SimpleNamespace(id=1, public_id=uuid4())

    db = MagicMock()
    # first with_for_update pending claim
    first = MagicMock()
    first.first.return_value = job
    db.scalars.return_value = first
    db.get.return_value = league

    monkeypatch.setattr(
        "app.services.sync.sync_league_fixtures",
        lambda *_a, **_k: {
            "ok": True,
            "created": 1,
            "updated": 2,
            "changed": 1,
            "scored": 1,
            "cascaded": 0,
            "skipped_missing_snapshot": 0,
            "skipped_missing_teams": 0,
            "changed_matches": [object()],
        },
    )

    out = run_league_job(db, job_id, MagicMock())
    assert out.status == "succeeded"
    assert out.summary is not None
    assert out.summary.get("created") == 1
    assert "changed_matches" not in (out.summary or {})
    assert out.finished_at is not None


def test_run_league_job_sync_failure(monkeypatch):
    job_id = uuid4()
    job = _job(public_id=job_id, status="pending", kind="sync")
    league = SimpleNamespace(id=1, public_id=uuid4())

    db = MagicMock()
    first = MagicMock()
    first.first.return_value = job
    db.scalars.return_value = first
    db.get.return_value = league

    monkeypatch.setattr(
        "app.services.sync.sync_league_fixtures",
        lambda *_a, **_k: {"ok": False, "error": "sync already in progress", "status_code": 409},
    )

    out = run_league_job(db, job_id, MagicMock())
    assert out.status == "failed"
    assert out.error == "sync already in progress"


def test_run_league_job_exception_preserves_original_when_refetch_misses(monkeypatch):
    job_id = uuid4()
    job = _job(public_id=job_id, status="pending", kind="sync")
    league = SimpleNamespace(id=1, public_id=uuid4())

    db = MagicMock()
    claim = MagicMock()
    claim.first.return_value = job
    miss = MagicMock()
    miss.first.return_value = None
    db.scalars.side_effect = [claim, miss]
    db.get.return_value = league

    monkeypatch.setattr(
        "app.services.sync.sync_league_fixtures",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("provider boom")),
    )

    with pytest.raises(RuntimeError, match="provider boom"):
        run_league_job(db, job_id, MagicMock())


def test_run_league_job_exception_marks_failed(monkeypatch):
    job_id = uuid4()
    job = _job(public_id=job_id, status="pending", kind="sync")
    league = SimpleNamespace(id=1, public_id=uuid4())
    refreshed = _job(public_id=job_id, status="running", kind="sync")

    db = MagicMock()
    claim = MagicMock()
    claim.first.return_value = job
    after_rollback = MagicMock()
    after_rollback.first.return_value = refreshed
    db.scalars.side_effect = [claim, after_rollback]
    db.get.return_value = league

    monkeypatch.setattr(
        "app.services.sync.sync_league_fixtures",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("provider boom")),
    )

    out = run_league_job(db, job_id, MagicMock())
    assert out is refreshed
    assert out.status == "failed"
    assert out.error == "provider boom"
    assert out.finished_at is not None


def test_run_league_job_recompute(monkeypatch):
    job_id = uuid4()
    job = _job(public_id=job_id, status="pending", kind="recompute")
    league = SimpleNamespace(id=1, public_id=uuid4())

    db = MagicMock()
    first = MagicMock()
    first.first.return_value = job
    db.scalars.return_value = first
    db.get.return_value = league

    monkeypatch.setattr(
        jobs_mod,
        "recompute_league_scores",
        lambda *_a, **_k: {
            "finished_matches": 10,
            "scored": 10,
            "cascaded": 3,
            "skipped_missing_snapshot": 0,
        },
    )

    out = run_league_job(db, job_id, MagicMock())
    assert out.status == "succeeded"
    assert out.summary["finished_matches"] == 10


def test_sync_all_records_cron_jobs(monkeypatch):
    from app.services import sync as sync_mod

    league_a = SimpleNamespace(id=1, public_id=uuid4(), upset_rules={})
    league_b = SimpleNamespace(id=2, public_id=uuid4(), upset_rules={})
    pool = SimpleNamespace(
        id=10,
        provider="football-data.org",
        competition_code="PL",
        season_year=2025,
        scores_match_results=True,
    )
    recorded: list[tuple[int, bool]] = []

    def fake_sync(db, provider, *, provider_key, competition_code, season_year):
        return {
            "ok": True,
            "created": 0,
            "updated": 0,
            "skipped_missing_teams": 0,
            "changed_matches": [],
        }

    def fake_record(db, league, *, ok, summary=None, error=None):
        recorded.append((league.id, ok))
        return _job(league_id=league.id, source="cron", status="succeeded" if ok else "failed")

    monkeypatch.setattr(sync_mod, "sync_competition_fixtures", fake_sync)
    monkeypatch.setattr(sync_mod, "ensure_fixed_ranking_for_league", lambda *_a, **_k: None)
    monkeypatch.setattr(sync_mod, "scoring_pools_for_league", lambda *_a, **_k: [pool])
    monkeypatch.setattr(
        sync_mod,
        "score_changed_matches",
        lambda *_a, **_k: {"scored": 0, "cascaded": 0, "skipped_missing_snapshot": 0},
    )
    monkeypatch.setattr(sync_mod, "record_cron_league_result", fake_record)

    db = MagicMock()
    payload = sync_all_active_competitions_then_score(db, MagicMock(), [league_a, league_b])
    assert payload["ok"] is True
    assert recorded == [(1, True), (2, True)]


def test_history_retained_conceptually():
    """Full history: multiple cron rows can exist; latest helper picks newest."""
    older = _job(source="cron", status="succeeded")
    older.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    newer = _job(source="cron", status="succeeded")
    newer.created_at = datetime(2026, 7, 1, tzinfo=UTC)

    db = MagicMock()

    def fake_latest(_db, _lid, source):
        if source == "cron":
            return newer
        return None

    from app.services import league_jobs as mod

    original = mod._latest_for_source
    mod._latest_for_source = fake_latest  # type: ignore[assignment]
    try:
        latest = latest_jobs_for_league(db, 1)
    finally:
        mod._latest_for_source = original  # type: ignore[assignment]

    assert latest["cron"] is newer
    assert latest["manual"] is None
    # older is still a valid historical object (no prune API)
    assert older.status == "succeeded"
