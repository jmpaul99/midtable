"""Tests for league competition create/remove settings and readiness."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.providers.base import CompetitionSeasonInfo, RateLimitInfo
from app.routers.leagues_core import _competition_type_from_provider, update_settings
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


def test_competition_type_resolves_with_competition_identity():
    provider = MagicMock()
    provider.resolve_competition_season.return_value = (
        CompetitionSeasonInfo(
            code="CL",
            season_year=2026,
            start_date=None,
            end_date=None,
            available=True,
            competition_type="CUP",
        ),
        RateLimitInfo(),
    )

    assert _competition_type_from_provider(provider, "CL", 2026) == "CUP"
    provider.resolve_competition_season.assert_called_once_with("CL", 2026)


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


def test_update_settings_rejects_draft_style_after_draft_starts():
    league = _league(status="drafting")
    member = SimpleNamespace(id=1)
    payload = LeagueSettingsUpdate(draft_style="snake")
    with pytest.raises(HTTPException) as exc:
        update_settings(payload=payload, membership=(league, member), db=MagicMock())
    assert exc.value.status_code == 409
    assert "before the draft" in exc.value.detail


def test_update_settings_rejects_slot_count_after_draft_starts():
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
        if call_n["n"] == 1:
            out.all.return_value = [member]
        elif call_n["n"] == 2:
            out.all.return_value = [pool]
        else:
            out.first.return_value = pool
        return out

    db.scalars.side_effect = scalars_side_effect
    payload = LeagueSettingsUpdate(
        pools=[PoolSettingsPatch(id=pool_public_id, slot_count=6)]
    )
    with pytest.raises(HTTPException) as exc:
        update_settings(payload=payload, membership=(league, member), db=db)
    assert exc.value.status_code == 409
    assert "slots" in exc.value.detail.lower()


def test_update_settings_rejects_competition_change_after_draft_starts():
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
        if call_n["n"] == 1:
            out.all.return_value = [member]
        elif call_n["n"] == 2:
            out.all.return_value = [pool]
        else:
            out.first.return_value = pool
        return out

    db.scalars.side_effect = scalars_side_effect
    payload = LeagueSettingsUpdate(
        pools=[PoolSettingsPatch(id=pool_public_id, competition_code="ELC")]
    )
    with pytest.raises(HTTPException) as exc:
        update_settings(payload=payload, membership=(league, member), db=db)
    assert exc.value.status_code == 409
    assert "competition" in exc.value.detail.lower()


def test_update_settings_rejects_season_year_after_draft_starts():
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
        if call_n["n"] == 1:
            out.all.return_value = [member]
        elif call_n["n"] == 2:
            out.all.return_value = [pool]
        else:
            out.first.return_value = pool
        return out

    db.scalars.side_effect = scalars_side_effect
    payload = LeagueSettingsUpdate(
        pools=[PoolSettingsPatch(id=pool_public_id, season_year=2025)]
    )
    with pytest.raises(HTTPException) as exc:
        update_settings(payload=payload, membership=(league, member), db=db)
    assert exc.value.status_code == 409
    assert "season year" in exc.value.detail.lower()


def test_update_settings_allows_draft_style_in_pre_draft():
    league = _league(status="pre_draft")
    league.draft_style = "linear"
    league.preassign_mode = "off"
    league.preassign_count = 1
    member = SimpleNamespace(id=1)
    db = MagicMock()
    detail = SimpleNamespace(id=league.id)
    payload = LeagueSettingsUpdate(draft_style="snake", preassign_mode="required")
    with patch("app.routers.leagues_core._league_detail", return_value=detail):
        result = update_settings(payload=payload, membership=(league, member), db=db)
    assert result is detail
    assert league.draft_style == "snake"
    assert league.preassign_mode == "required"
    db.commit.assert_called_once()


def test_update_settings_clears_preassigns_when_mode_becomes_off():
    league = _league(status="pre_draft")
    league.draft_style = "linear"
    league.preassign_mode = "required"
    league.preassign_count = 1
    member = SimpleNamespace(id=1)
    entry = SimpleNamespace(id=99, league_id=league.id, source="preassigned")
    db = MagicMock()
    scalars_out = MagicMock()
    scalars_out.all.return_value = [entry]
    db.scalars.return_value = scalars_out
    detail = SimpleNamespace(id=league.id)
    payload = LeagueSettingsUpdate(preassign_mode="off")
    with patch("app.routers.leagues_core._league_detail", return_value=detail):
        update_settings(payload=payload, membership=(league, member), db=db)
    assert league.preassign_mode == "off"
    db.delete.assert_called_once_with(entry)
    db.flush.assert_called()
    db.commit.assert_called_once()


def test_update_settings_rejects_required_with_zero_count():
    league = _league(status="pre_draft")
    league.preassign_mode = "optional"
    league.preassign_count = 0
    member = SimpleNamespace(id=1)
    payload = LeagueSettingsUpdate(preassign_mode="required")
    with pytest.raises(HTTPException) as exc:
        update_settings(payload=payload, membership=(league, member), db=MagicMock())
    assert exc.value.status_code == 400
    assert "at least 1" in str(exc.value.detail).lower()


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
    from app.services.readiness import evaluate_readiness

    league = _league(status="pre_draft")
    db = MagicMock()

    def scalars_side_effect(stmt):
        out = MagicMock()
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars_side_effect

    result = evaluate_readiness(db, league, purpose="draft")
    pools_check = next(c for c in result.checks if c.key == "pools")
    assert pools_check.status == "error"
    assert "League settings" in (pools_check.detail or "")
    assert result.ready is False


def test_readiness_pools_check_ok_with_competition():
    from app.services.readiness import evaluate_readiness

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
        # 1: pools, 2: members, then per-pool teams
        if call_n["n"] == 1:
            out.all.return_value = [pool]
        elif call_n["n"] == 2:
            out.all.return_value = [member]
        else:
            out.all.return_value = [SimpleNamespace(id=1)]  # teams
        return out

    db.scalars.side_effect = scalars_side_effect
    result = evaluate_readiness(db, league, purpose="draft")
    pools_check = next(c for c in result.checks if c.key == "pools")
    assert pools_check.status == "ok"


def test_draft_readiness_provider_missing_is_warning_only():
    from app.services.readiness import evaluate_readiness

    league = _league(status="pre_draft")
    league.config = {"max_members": 2}
    members = [
        SimpleNamespace(id=1, draft_slot=1),
        SimpleNamespace(id=2, draft_slot=2),
    ]
    pool = SimpleNamespace(
        id=1,
        key="premier_league",
        label="Premier League",
        slot_count=5,
        scores_match_results=True,
        competition_code=None,
        season_year=None,
    )
    db = MagicMock()
    call_n = {"n": 0}

    def scalars_side_effect(_stmt):
        out = MagicMock()
        call_n["n"] += 1
        if call_n["n"] == 1:
            out.all.return_value = [pool]
        elif call_n["n"] == 2:
            out.all.return_value = members
        else:
            out.all.return_value = [SimpleNamespace(id=1)]
        return out

    db.scalars.side_effect = scalars_side_effect
    result = evaluate_readiness(db, league, purpose="draft")
    provider = next(c for c in result.checks if c.key.startswith("provider:"))
    assert provider.status == "warning"
    assert result.ready is True
    assert "members" in {c.key for c in result.checks}


def test_sync_readiness_ignores_members_errors_on_provider():
    from app.services.readiness import evaluate_readiness

    league = _league(status="pre_draft")
    # Incomplete roster would fail draft readiness
    league.config = {"max_members": 4}
    pool = SimpleNamespace(
        id=1,
        key="premier_league",
        label="Premier League",
        slot_count=5,
        scores_match_results=True,
        competition_code=None,
        season_year=2026,
    )
    db = MagicMock()
    call_n = {"n": 0}

    def scalars_side_effect(_stmt):
        out = MagicMock()
        call_n["n"] += 1
        if call_n["n"] == 1:
            out.all.return_value = [pool]
        else:
            out.all.return_value = []  # no pool teams
        return out

    db.scalars.side_effect = scalars_side_effect
    result = evaluate_readiness(db, league, purpose="sync")
    assert "members" not in {c.key for c in result.checks}
    assert "draft_order" not in {c.key for c in result.checks}
    provider = next(c for c in result.checks if c.key.startswith("provider:"))
    assert provider.status == "error"
    assert result.ready is False


def test_sync_readiness_ok_without_full_roster():
    from app.services.readiness import evaluate_readiness

    league = _league(status="pre_draft")
    league.config = {"max_members": 8}
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

    def scalars_side_effect(_stmt):
        out = MagicMock()
        call_n["n"] += 1
        if call_n["n"] == 1:
            out.all.return_value = [pool]
        else:
            out.all.return_value = []  # empty clubs = warning only for sync
        return out

    db.scalars.side_effect = scalars_side_effect
    result = evaluate_readiness(db, league, purpose="sync")
    teams = next(c for c in result.checks if c.key.startswith("teams:"))
    assert teams.status == "warning"
    assert result.ready is True


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


def test_sync_league_fixtures_skips_ranking_ensure_before_pull(monkeypatch):
    from app.services import sync as sync_mod

    league = _league()
    league.upset_rules = {}
    pool = SimpleNamespace(
        id=1,
        key="pl",
        scores_match_results=True,
        provider="football-data.org",
        competition_code="PL",
        season_year=2026,
    )
    db = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [pool]
    db.scalars.return_value = scalars

    ensure_calls = {"n": 0}

    def track_ensure(*_a, **_k):
        ensure_calls["n"] += 1

    monkeypatch.setattr(sync_mod, "ensure_fixed_ranking_for_league", track_ensure)
    monkeypatch.setattr(
        sync_mod,
        "sync_competition_fixtures",
        lambda *_a, **_k: {
            "ok": True,
            "created": 0,
            "updated": 0,
            "skipped_missing_teams": 0,
            "changed_matches": [],
        },
    )
    monkeypatch.setattr(
        sync_mod,
        "score_changed_matches",
        lambda *_a, **_k: {"scored": 0, "cascaded": 0, "skipped_missing_snapshot": 0},
    )

    result = sync_league_fixtures(db, league, provider=MagicMock())
    assert result["ok"] is True
    # ensure runs inside score_changed_matches (mocked), not before competition pull
    assert ensure_calls["n"] == 0


def test_readiness_check_model():
    check = ReadinessCheck(
        key="pools",
        label="Competitions configured",
        status="error",
        detail="Add competitions",
    )
    assert check.status == "error"


def test_readiness_required_preassigns_exact_count():
    from app.services.readiness import evaluate_readiness

    league = _league(status="pre_draft")
    league.config = {"max_members": 2}
    league.preassign_mode = "required"
    league.preassign_count = 2
    members = [
        SimpleNamespace(id=10, draft_slot=1),
        SimpleNamespace(id=11, draft_slot=2),
    ]
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

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "team_pool" in sql:
            out.all.return_value = [pool]
            return out
        if "league_member" in sql:
            out.all.return_value = members
            return out
        if "roster" in sql:
            out.all.return_value = [
                SimpleNamespace(member_id=10, team_id=1, source="preassigned"),
                SimpleNamespace(member_id=10, team_id=2, source="preassigned"),
            ]
            return out
        out.all.return_value = [SimpleNamespace(id=1)]
        return out

    db.scalars.side_effect = scalars
    result = evaluate_readiness(db, league, purpose="draft")
    pre = next(c for c in result.checks if c.key == "preassigns")
    assert pre.status == "error"
    assert "exactly 2" in (pre.detail or "")
    assert result.ready is False


def test_readiness_optional_preassigns_allows_zero_errors_on_over_max():
    from app.services.readiness import evaluate_readiness

    league = _league(status="pre_draft")
    league.config = {"max_members": 2}
    league.preassign_mode = "optional"
    league.preassign_count = 1
    members = [
        SimpleNamespace(id=10, draft_slot=1),
        SimpleNamespace(id=11, draft_slot=2),
    ]
    pool = SimpleNamespace(
        id=1,
        key="premier_league",
        label="Premier League",
        slot_count=5,
        scores_match_results=True,
        competition_code="PL",
        season_year=2026,
    )

    def make_db(preassigns):
        db = MagicMock()

        def scalars(stmt):
            sql = str(stmt).lower()
            out = MagicMock()
            if "team_pool" in sql:
                out.all.return_value = [pool]
                return out
            if "league_member" in sql:
                out.all.return_value = members
                return out
            if "roster" in sql:
                out.all.return_value = preassigns
                return out
            out.all.return_value = [SimpleNamespace(id=1)]
            return out

        db.scalars.side_effect = scalars
        return db

    ok = evaluate_readiness(make_db([]), league, purpose="draft")
    pre_ok = next(c for c in ok.checks if c.key == "preassigns")
    assert pre_ok.status == "ok"

    over = evaluate_readiness(
        make_db(
            [
                SimpleNamespace(member_id=10, team_id=1, source="preassigned"),
                SimpleNamespace(member_id=10, team_id=2, source="preassigned"),
            ]
        ),
        league,
        purpose="draft",
    )
    pre_over = next(c for c in over.checks if c.key == "preassigns")
    assert pre_over.status == "error"
    assert over.ready is False


def test_league_response_preserves_zero_preassign_count():
    from decimal import Decimal

    from app.routers.league_mappers import _league_response

    league = SimpleNamespace(
        public_id=uuid4(),
        name="Test",
        season_label="2026-27",
        status="pre_draft",
        draft_style="linear",
        preassign_mode="optional",
        preassign_count=0,
        result_points={"win": 3},
        upset_rules={},
        leaderboard_phases=[],
        leaderboard_tiebreaks=[],
        buy_in=Decimal("0"),
        payouts=[],
        scheduled_start_date=None,
        scheduled_end_date=None,
        draft_scheduled_at=None,
        pick_timer_seconds=None,
        template_id=None,
        config={"max_members": 4},
    )
    resp = _league_response(league)
    assert resp.preassign_count == 0


def test_effective_preassign_count_keeps_zero():
    from app.services.preassign import effective_preassign_count

    assert effective_preassign_count(0) == 0
    assert effective_preassign_count(None) == 1
    assert effective_preassign_count(3) == 3


def test_readiness_errors_when_preassigns_exceed_pool_slot_count():
    from app.services.readiness import evaluate_readiness

    league = _league(status="pre_draft")
    league.config = {"max_members": 2}
    league.preassign_mode = "optional"
    league.preassign_count = 5
    members = [
        SimpleNamespace(id=10, draft_slot=1),
        SimpleNamespace(id=11, draft_slot=2),
    ]
    pool = SimpleNamespace(
        id=1,
        key="cup",
        label="Cup",
        slot_count=1,
        scores_match_results=True,
        competition_code="PL",
        season_year=2026,
    )
    db = MagicMock()

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "team_pool" in sql:
            out.all.return_value = [pool]
            return out
        if "league_member" in sql:
            out.all.return_value = members
            return out
        if "roster" in sql:
            out.all.return_value = [
                SimpleNamespace(
                    member_id=10, team_id=1, pool_id=1, source="preassigned"
                ),
                SimpleNamespace(
                    member_id=10, team_id=2, pool_id=1, source="preassigned"
                ),
            ]
            return out
        out.all.return_value = [SimpleNamespace(id=1)]
        return out

    db.scalars.side_effect = scalars
    result = evaluate_readiness(db, league, purpose="draft")
    slots = next(c for c in result.checks if c.key == "preassigns:pool_slots")
    assert slots.status == "error"
    assert result.ready is False


def test_preassign_rejects_when_pool_slot_full():
    from app.routers.draft import preassign_team
    from app.schemas.leagues import PreassignRequest

    member_id = uuid4()
    pool_id = uuid4()
    team_id = uuid4()
    league = SimpleNamespace(
        id=1,
        public_id=uuid4(),
        status="pre_draft",
        preassign_mode="optional",
        preassign_count=5,
    )
    member = SimpleNamespace(id=10, public_id=member_id)
    pool = SimpleNamespace(id=20, public_id=pool_id, slot_count=1, league_id=1)
    commissioner = SimpleNamespace(id=99)
    db = MagicMock()
    roster_calls = {"n": 0}

    def scalars(stmt):
        sql = str(stmt).lower()
        out = MagicMock()
        if "league_member" in sql:
            out.first.return_value = member
            return out
        if "team_pool" in sql:
            out.first.return_value = pool
            return out
        if "roster" in sql:
            roster_calls["n"] += 1
            # 1st: league-wide preassign limit check (under limit)
            # 2nd: member_pool_filled (already at slot_count)
            out.all.return_value = (
                [] if roster_calls["n"] == 1 else [SimpleNamespace(id=1)]
            )
            return out
        out.first.return_value = None
        out.all.return_value = []
        return out

    db.scalars.side_effect = scalars
    payload = PreassignRequest(member_id=member_id, pool_id=pool_id, team_id=team_id)
    with pytest.raises(HTTPException) as exc:
        preassign_team(payload=payload, membership=(league, commissioner), db=db)
    assert exc.value.status_code == 409
    assert "competition is full" in str(exc.value.detail).lower()
