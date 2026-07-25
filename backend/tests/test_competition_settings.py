"""Tests for league competition create/remove settings and readiness."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.leagues_core import update_settings
from app.schemas.leagues import LeagueSettingsUpdate, PoolSettingsPatch, ReadinessCheck
from app.services.competitions import AVAILABLE_COMPETITION_CODES, is_allowed_competition_code
from app.services.sync import sync_league_fixtures


def test_allowlist_contains_free_plan_codes():
    assert "PL" in AVAILABLE_COMPETITION_CODES
    assert "ELC" in AVAILABLE_COMPETITION_CODES
    assert is_allowed_competition_code("pl")
    assert not is_allowed_competition_code("XYZ")


def test_pool_settings_rejects_unknown_competition_code():
    with pytest.raises(ValidationError):
        PoolSettingsPatch(
            key="mystery",
            label="Mystery League",
            slot_count=1,
            competition_code="XYZ",
            season_year=2026,
        )


def test_pool_settings_create_requires_fields():
    with pytest.raises(ValidationError):
        PoolSettingsPatch(label="Premier League")


def test_pool_settings_create_accepts_allowed_code():
    patch_item = PoolSettingsPatch(
        key="premier_league",
        label="Premier League",
        slot_count=5,
        competition_code="pl",
        season_year=2026,
    )
    assert patch_item.competition_code == "PL"
    assert patch_item.id is None


def _league(*, status: str = "pre_draft", lid: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=lid,
        status=status,
        config={"max_members": 4},
        name="Test",
        season_label="2026-27",
    )


def test_update_settings_rejects_create_after_draft_starts():
    league = _league(status="drafting")
    member = SimpleNamespace(id=1)
    payload = LeagueSettingsUpdate(
        pools=[
            PoolSettingsPatch(
                key="premier_league",
                label="Premier League",
                slot_count=5,
                competition_code="PL",
                season_year=2026,
            )
        ]
    )
    with pytest.raises(HTTPException) as exc:
        update_settings(payload=payload, membership=(league, member), db=MagicMock())
    assert exc.value.status_code == 409
    assert "before the draft" in exc.value.detail


def test_update_settings_rejects_remove_after_draft_starts():
    league = _league(status="drafting")
    member = SimpleNamespace(id=1)
    payload = LeagueSettingsUpdate(remove_pool_ids=[uuid4()])
    with pytest.raises(HTTPException) as exc:
        update_settings(payload=payload, membership=(league, member), db=MagicMock())
    assert exc.value.status_code == 409


def test_update_settings_creates_pool_in_pre_draft():
    league = _league(status="pre_draft")
    member = SimpleNamespace(id=1, public_id=uuid4())
    db = MagicMock()

    empty = MagicMock()
    empty.all.return_value = []
    empty.first.return_value = None

    def scalars_side_effect(stmt):
        out = MagicMock()
        out.all.return_value = []
        out.first.return_value = None
        return out

    db.scalars.side_effect = scalars_side_effect

    payload = LeagueSettingsUpdate(
        pools=[
            PoolSettingsPatch(
                key="premier_league",
                label="Premier League",
                slot_count=5,
                sort_order=1,
                competition_code="PL",
                season_year=2026,
                scores_match_results=True,
            )
        ]
    )

    detail = SimpleNamespace(id=league.id)
    with patch("app.routers.leagues_core._league_detail", return_value=detail):
        result = update_settings(payload=payload, membership=(league, member), db=db)

    assert result is detail
    assert db.add.called
    created = db.add.call_args[0][0]
    assert created.key == "premier_league"
    assert created.competition_code == "PL"
    assert created.season_year == 2026
    db.commit.assert_called_once()


def test_update_settings_removes_pool_in_pre_draft():
    league = _league(status="pre_draft")
    member = SimpleNamespace(id=1, public_id=uuid4())
    pool_public_id = uuid4()
    pool = SimpleNamespace(id=10, public_id=pool_public_id, league_id=league.id)

    db = MagicMock()
    out = MagicMock()
    out.first.return_value = pool
    db.scalars.return_value = out

    payload = LeagueSettingsUpdate(remove_pool_ids=[pool_public_id])
    detail = SimpleNamespace(id=league.id)
    with patch("app.routers.leagues_core._league_detail", return_value=detail):
        update_settings(payload=payload, membership=(league, member), db=db)

    db.delete.assert_called_once_with(pool)
    db.commit.assert_called_once()


def test_update_settings_update_only_allowed_when_drafting():
    league = _league(status="drafting")
    member = SimpleNamespace(id=1, public_id=uuid4())
    pool_public_id = uuid4()
    pool = SimpleNamespace(
        id=10,
        public_id=pool_public_id,
        league_id=league.id,
        key="premier_league",
        label="Premier League",
        competition_code="PL",
        season_year=2026,
        sort_order=1,
        slot_count=5,
        scores_match_results=True,
        provider="football-data.org",
    )

    db = MagicMock()
    call_n = {"n": 0}

    def scalars_side_effect(stmt):
        out = MagicMock()
        call_n["n"] += 1
        # 1) members, 2) existing pools, 3) pool by id, 4) pool teams
        if call_n["n"] == 1:
            out.all.return_value = [member]
        elif call_n["n"] == 2:
            out.all.return_value = [pool]
        elif call_n["n"] == 3:
            out.first.return_value = pool
        else:
            out.all.return_value = [SimpleNamespace(id=1)] * 20
        return out

    db.scalars.side_effect = scalars_side_effect

    payload = LeagueSettingsUpdate(
        pools=[
            PoolSettingsPatch(
                id=pool_public_id,
                label="PL Updated",
                slot_count=5,
            )
        ]
    )
    detail = SimpleNamespace(id=league.id)
    with patch("app.routers.leagues_core._league_detail", return_value=detail):
        update_settings(payload=payload, membership=(league, member), db=db)

    assert pool.label == "PL Updated"
    db.add.assert_not_called()
    db.delete.assert_not_called()
    db.commit.assert_called_once()


def test_readiness_pools_check_errors_without_competitions():
    from app.routers.league_ops import readiness

    league = _league(status="pre_draft")
    member = SimpleNamespace(id=1)
    db = MagicMock()

    def scalars_side_effect(stmt):
        out = MagicMock()
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars_side_effect

    result = readiness(membership=(league, member), db=db)
    pools_check = next(c for c in result.checks if c.key == "pools")
    assert pools_check.status == "error"
    assert "League settings" in (pools_check.detail or "")
    assert result.ready is False


def test_readiness_pools_check_ok_with_competition():
    from app.routers.league_ops import readiness

    league = _league(status="pre_draft")
    member = SimpleNamespace(id=1, draft_slot=1)
    pool = SimpleNamespace(
        id=1,
        key="premier_league",
        label="Premier League",
        slot_count=5,
        scores_match_results=True,
        competition_code="PL",
        season_year=2026,
    )
    db = MagicMock()

    call_n = {"n": 0}

    def scalars_side_effect(stmt):
        out = MagicMock()
        call_n["n"] += 1
        # First: members, second: pools, then per-pool teams
        if call_n["n"] == 1:
            out.all.return_value = [member]
        elif call_n["n"] == 2:
            out.all.return_value = [pool]
        else:
            out.all.return_value = [SimpleNamespace(id=1)]  # teams
        return out

    db.scalars.side_effect = scalars_side_effect
    # max_members configured via league.config
    result = readiness(membership=(league, member), db=db)
    pools_check = next(c for c in result.checks if c.key == "pools")
    assert pools_check.status == "ok"


def test_sync_fails_without_competitions():
    league = _league()
    db = MagicMock()
    out = MagicMock()
    out.all.return_value = []
    db.scalars.return_value = out

    result = sync_league_fixtures(db, league, provider=MagicMock())
    assert result["ok"] is False
    assert result["status_code"] == 400
    assert "No competitions" in result["error"]


def test_readiness_check_model():
    check = ReadinessCheck(
        key="pools",
        label="Competitions configured",
        status="error",
        detail="Add competitions",
    )
    assert check.status == "error"
