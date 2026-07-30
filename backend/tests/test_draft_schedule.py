"""Tests for draft_scheduled_at validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.leagues_core import update_settings
from app.schemas.leagues import LeagueSettingsUpdate
from app.services.draft_schedule import (
    earliest_kickoff_for_keys,
    validate_draft_scheduled_at,
)
from app.services.errors import DomainError


def test_validate_allows_none():
    validate_draft_scheduled_at(MagicMock(), None)


def test_validate_rejects_past():
    now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    with pytest.raises(DomainError, match="in the future"):
        validate_draft_scheduled_at(
            MagicMock(),
            now - timedelta(minutes=1),
            now=now,
        )


def test_validate_rejects_on_or_after_first_match():
    now = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    first = datetime(2026, 8, 15, 15, 0, tzinfo=UTC)
    db = MagicMock()
    with patch(
        "app.services.draft_schedule.earliest_kickoff_for_keys",
        return_value=first,
    ):
        with pytest.raises(DomainError, match="before the first match"):
            validate_draft_scheduled_at(
                db,
                first,
                competition_keys=[("football-data.org", "PL", 2026)],
                now=now,
            )
        with pytest.raises(DomainError, match="before the first match"):
            validate_draft_scheduled_at(
                db,
                first + timedelta(hours=1),
                competition_keys=[("football-data.org", "PL", 2026)],
                now=now,
            )


def test_validate_allows_before_first_match():
    now = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    first = datetime(2026, 8, 15, 15, 0, tzinfo=UTC)
    db = MagicMock()
    with patch(
        "app.services.draft_schedule.earliest_kickoff_for_keys",
        return_value=first,
    ):
        validate_draft_scheduled_at(
            db,
            first - timedelta(hours=1),
            competition_keys=[("football-data.org", "PL", 2026)],
            now=now,
        )


def test_validate_skips_first_match_when_unknown():
    now = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    db = MagicMock()
    with patch(
        "app.services.draft_schedule.earliest_kickoff_for_keys",
        return_value=None,
    ):
        validate_draft_scheduled_at(
            db,
            now + timedelta(days=30),
            competition_keys=[("football-data.org", "PL", 2026)],
            now=now,
        )


def test_earliest_kickoff_normalizes_codes():
    db = MagicMock()
    db.scalar.return_value = datetime(2026, 8, 15, 15, 0, tzinfo=UTC)
    result = earliest_kickoff_for_keys(db, [("football-data.org", "pl", 2026)])
    assert result == datetime(2026, 8, 15, 15, 0, tzinfo=UTC)
    db.scalar.assert_called_once()


def test_update_settings_rejects_past_draft_schedule():
    league = SimpleNamespace(
        id=1,
        status="pre_draft",
        config={"max_members": 4},
        name="Test",
        season_label="2026-27",
        draft_style="linear",
        preassign_mode="off",
        preassign_count=1,
    )
    member = SimpleNamespace(id=1, public_id=uuid4())
    now = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    payload = LeagueSettingsUpdate(
        draft_scheduled_at=now - timedelta(days=1),
    )
    db = MagicMock()
    draft_state = SimpleNamespace(status="pending")
    db.scalars.return_value.first.return_value = draft_state

    with patch(
        "app.routers.leagues_core.validate_draft_scheduled_at",
        side_effect=DomainError("Draft start must be in the future."),
    ):
        with pytest.raises(HTTPException) as exc:
            update_settings(payload=payload, membership=(league, member), db=db)
    assert exc.value.status_code == 400
    assert "future" in str(exc.value.detail)
