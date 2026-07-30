"""Platform job enqueue/run/latest and cron persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models import PlatformJob
from app.services.platform_jobs import (
    ActivePlatformJobConflict,
    enqueue_platform_job,
    json_safe_fifa_summary,
    latest_platform_jobs,
    record_cron_platform_result,
    run_platform_job,
)


def _job(
    *,
    kind: str = "teams_and_rankings",
    source: str = "admin",
    status: str = "pending",
    public_id=None,
) -> PlatformJob:
    job = PlatformJob(
        kind=kind,
        source=source,
        status=status,
        created_by_profile_id=None,
        params=None,
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
    existing = _job(status="running")
    db = MagicMock()
    db.scalars.return_value.first.return_value = existing

    with pytest.raises(ActivePlatformJobConflict) as exc:
        enqueue_platform_job(db, kind="teams_and_rankings", created_by_profile_id=9)
    assert exc.value.job is existing
    db.add.assert_not_called()


def test_enqueue_creates_pending_job():
    db = MagicMock()
    db.scalars.return_value.first.return_value = None

    def refresh(job):
        job.public_id = uuid4()
        job.created_at = datetime.now(UTC)

    db.refresh.side_effect = refresh

    job = enqueue_platform_job(
        db,
        kind="teams_and_rankings",
        created_by_profile_id=3,
        params={"season_year": 2025},
    )
    assert job.kind == "teams_and_rankings"
    assert job.source == "admin"
    assert job.status == "pending"
    assert job.created_by_profile_id == 3
    assert job.params == {"season_year": 2025}
    db.add.assert_called_once()
    db.commit.assert_called()


def test_latest_jobs_independent_per_source():
    manual = _job(source="admin", kind="teams_and_rankings", status="succeeded")
    cron = _job(source="cron", kind="fifa_rankings", status="succeeded")

    from app.services import platform_jobs as mod

    calls: list[str] = []

    def fake_latest(_db, source):
        calls.append(source)
        return manual if source == "admin" else cron

    original = mod._latest_for_source
    mod._latest_for_source = fake_latest  # type: ignore[assignment]
    try:
        latest = latest_platform_jobs(MagicMock())
    finally:
        mod._latest_for_source = original  # type: ignore[assignment]

    assert latest["manual"] is manual
    assert latest["cron"] is cron
    assert calls == ["admin", "cron"]


def test_record_cron_platform_result():
    db = MagicMock()
    job = record_cron_platform_result(
        db,
        kind="fifa_rankings",
        ok=True,
        summary={"ok": True, "rankings_catalogs": {"men": {"entries": 10}}},
    )
    assert job.source == "cron"
    assert job.status == "succeeded"
    assert job.kind == "fifa_rankings"
    db.add.assert_called()
    db.flush.assert_called()


def test_json_safe_fifa_summary():
    out = json_safe_fifa_summary(
        {
            "ok": True,
            "catalogs": {
                "men": {"entries": 50, "leagues_updated": 2},
                "women": {"entries": 40},
            },
        }
    )
    assert out["ok"] is True
    assert out["rankings_catalogs"]["men"] == {"entries": 50}
    assert out["rankings_catalogs"]["women"] == {"entries": 40}


def test_run_platform_job_success(monkeypatch):
    job_id = uuid4()
    job = _job(public_id=job_id, status="pending")
    job.params = {"season_year": 2025}

    db = MagicMock()
    first = MagicMock()
    first.first.return_value = job
    db.scalars.return_value = first

    monkeypatch.setattr(
        "app.services.global_sync.sync_all_teams_and_rankings",
        lambda *_a, **_k: {
            "ok": True,
            "season_year": 2025,
            "teams": {
                "ok": True,
                "created": 2,
                "updated": 5,
                "competitions_ok": 3,
                "competitions_total": 3,
            },
            "rankings": {"ok": True, "catalogs": {"men": {"entries": 10}}},
            "table_snapshots": {
                "ok": True,
                "created_previous_final": 1,
                "created_zeroed_opener": 1,
            },
        },
    )

    settings = MagicMock()
    out = run_platform_job(db, job_id, MagicMock(), settings)
    assert out.status == "succeeded"
    assert out.summary is not None
    assert out.summary.get("teams_created") == 2
    assert out.summary.get("season_year") == 2025
    assert out.finished_at is not None


def test_run_platform_job_teams_failure(monkeypatch):
    job_id = uuid4()
    job = _job(public_id=job_id, status="pending")

    db = MagicMock()
    first = MagicMock()
    first.first.return_value = job
    db.scalars.return_value = first

    monkeypatch.setattr(
        "app.services.global_sync.sync_all_teams_and_rankings",
        lambda *_a, **_k: {
            "ok": False,
            "season_year": 2025,
            "teams": {"ok": False, "error": "provider down"},
            "rankings": {"ok": False, "skipped": True},
            "table_snapshots": {},
        },
    )

    out = run_platform_job(db, job_id, MagicMock(), MagicMock())
    assert out.status == "failed"
    assert out.error == "provider down"


def test_global_sync_ok_requires_table_snapshots(monkeypatch):
    from app.services.global_sync import sync_all_teams_and_rankings

    monkeypatch.setattr(
        "app.services.global_sync.upsert_teams_for_competitions",
        lambda *_a, **_k: {
            "ok": True,
            "created": 1,
            "updated": 0,
            "competitions": [{"ok": True, "code": "PL", "season_year": 2025}],
        },
    )
    monkeypatch.setattr(
        "app.services.global_sync.ensure_table_baselines_for_competitions",
        lambda *_a, **_k: {
            "ok": False,
            "competitions_ok": 0,
            "competitions_failed": 1,
            "created_previous_final": 0,
            "created_zeroed_opener": 0,
            "competitions": [{"code": "PL", "ok": False, "error": "429"}],
        },
    )
    settings = MagicMock()
    settings.parse_api_key = "   "  # skipped rankings
    payload = sync_all_teams_and_rankings(
        MagicMock(),
        MagicMock(),
        settings=settings,
        season_year=2025,
    )
    assert payload["ok"] is False
    assert payload["table_snapshots"]["ok"] is False
    assert payload["rankings"].get("skipped") is True
