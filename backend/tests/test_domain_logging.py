"""Caplog coverage for expanded domain logging."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth.jwt import AuthenticatedUser
from app.deps import require_platform_admin
from app.services.sync import score_changed_matches, sync_league_fixtures


def test_score_changed_matches_empty_logs(caplog: pytest.LogCaptureFixture):
    league = SimpleNamespace(public_id=uuid4())
    db = MagicMock()
    with caplog.at_level(logging.INFO, logger="app.services.sync"):
        summary = score_changed_matches(db, league, [])
    assert summary == {"scored": 0, "cascaded": 0, "skipped_missing_snapshot": 0}
    assert any("score_changed_matches empty" in r.getMessage() for r in caplog.records)


def test_sync_soft_fail_no_pools_logs(caplog: pytest.LogCaptureFixture):
    league = SimpleNamespace(public_id=uuid4(), id=1)
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with caplog.at_level(logging.WARNING, logger="app.services.sync"):
        result = sync_league_fixtures(db, league, MagicMock())
    assert result["ok"] is False
    assert result["status_code"] == 400
    assert any("reason=no_pools" in r.getMessage() for r in caplog.records)


def test_sync_soft_fail_in_progress_logs(caplog: pytest.LogCaptureFixture):
    from datetime import UTC, datetime

    league = SimpleNamespace(public_id=uuid4(), id=1)
    pool = SimpleNamespace(id=1)
    status = SimpleNamespace(
        in_progress=True,
        in_progress_since=datetime.now(UTC),
        last_error=None,
    )
    db = MagicMock()
    # first scalars().all() -> pools; _ensure_sync_status uses scalars().first()/one()
    scalars_result = MagicMock()
    scalars_result.all.return_value = [pool]
    scalars_result.first.return_value = status
    scalars_result.one.return_value = status
    db.scalars.return_value = scalars_result

    with caplog.at_level(logging.WARNING, logger="app.services.sync"):
        result = sync_league_fixtures(db, league, MagicMock())
    assert result["ok"] is False
    assert result["status_code"] == 409
    assert any("reason=in_progress" in r.getMessage() for r in caplog.records)


def test_authz_platform_admin_denied_logs(caplog: pytest.LogCaptureFixture):
    user = AuthenticatedUser(
        auth_user_id=None,
        email="manager@example.com",
        role="authenticated",
        claims={},
    )
    with caplog.at_level(logging.WARNING, logger="app.deps"):
        with pytest.raises(HTTPException) as exc_info:
            require_platform_admin(user=user)
    assert exc_info.value.status_code == 403
    assert any("not_platform_admin" in r.getMessage() for r in caplog.records)


def test_league_delete_logs_warning(caplog: pytest.LogCaptureFixture, monkeypatch):
    """Lifecycle WARNING path: delete_league logs before deleting."""
    from app.routers import leagues_core

    league = SimpleNamespace(
        public_id=uuid4(),
        name="Test League",
        status="pre_draft",
    )
    member = SimpleNamespace(public_id=uuid4())
    db = MagicMock()

    with caplog.at_level(logging.WARNING, logger="app.routers.leagues_core"):
        response = leagues_core.delete_league(
            membership=(league, member),
            db=db,
        )
    assert response.status_code == 204
    db.delete.assert_called_once_with(league)
    assert any("league deleted" in r.getMessage() for r in caplog.records)


def test_my_standing_value_error_logs_warning(caplog: pytest.LogCaptureFixture, monkeypatch):
    from app.routers import leagues_core

    league = SimpleNamespace(public_id=uuid4(), id=1)
    membership = SimpleNamespace(public_id=uuid4())
    db = MagicMock()
    db.scalars.return_value.all.return_value = [membership]

    def boom(*_args, **_kwargs):
        raise ValueError("unknown phase key: bad")

    monkeypatch.setattr(leagues_core.analytics_service, "leaderboard", boom)

    with caplog.at_level(logging.WARNING, logger="app.routers.leagues_core"):
        rank, count, points, has_scored = leagues_core._my_standing(db, league, membership)

    assert rank is None
    assert count == 1
    assert points is None
    assert has_scored is False
    assert any("leaderboard unavailable" in r.getMessage() for r in caplog.records)


def test_create_bonus_type_logs(caplog: pytest.LogCaptureFixture):
    from app.routers import admin
    from app.schemas.admin import BonusTypeCreate

    league = SimpleNamespace(public_id=uuid4(), id=1)
    member = SimpleNamespace(public_id=uuid4())
    db = MagicMock()

    def refresh(row):
        row.public_id = uuid4()

    db.refresh.side_effect = refresh
    payload = BonusTypeCreate(
        key="man_of_match",
        label="Man of the match",
        default_points=1,
        sort_order=0,
        include_in_phases=[],
    )

    with caplog.at_level(logging.INFO, logger="app.routers.admin"):
        result = admin.create_bonus_type(
            payload=payload,
            membership=(league, member),
            db=db,
        )

    assert "id" in result
    assert result["key"] == "man_of_match"
    assert any("bonus type created" in r.getMessage() for r in caplog.records)
