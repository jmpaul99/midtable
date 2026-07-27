"""Unit tests for bridge/harden correctness (no DB)."""

from datetime import UTC, datetime

from app.config import Settings
from app.services.draft import on_clock_member
from app.services.scoring import MatchInput, is_finished


def test_finished_requires_non_null_goals():
    kickoff = datetime(2026, 8, 15, 14, tzinfo=UTC)
    unfinished = MatchInput(
        match_id=1,
        pool_id=1,
        home_team_id=1,
        away_team_id=2,
        kickoff_at=kickoff,
        home_goals=None,
        away_goals=None,
        status="FINISHED",
    )
    assert not is_finished(unfinished)

    finished = MatchInput(
        match_id=1,
        pool_id=1,
        home_team_id=1,
        away_team_id=2,
        kickoff_at=kickoff,
        home_goals=0,
        away_goals=0,
        status="FINISHED",
    )
    assert is_finished(finished)


def test_production_rejects_default_secrets():
    settings = Settings(
        app_env="production",
        cron_secret="dev-cron-secret",
        auth_bypass_email="",
    )
    try:
        settings.validate_runtime()
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_production_rejects_auth_bypass():
    settings = Settings(
        app_env="production",
        cron_secret="secure-cron",
        supabase_url="https://example.supabase.co",
        auth_bypass_email="admin@example.com",
    )
    try:
        settings.validate_runtime()
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_snake_on_clock_reverses_even_rounds():
    class M:
        def __init__(self, slot: int, mid: int):
            self.draft_slot = slot
            self.id = mid
            self.public_id = mid

    ordered = [M(1, 10), M(2, 20), M(3, 30)]
    member, round_number = on_clock_member(
        draft_style="snake", ordered=ordered, pick_number=4
    )
    assert round_number == 2
    assert member.id == 30


def test_match_unique_constraint_is_competition_scoped():
    from app.models.entities import Match

    args = Match.__table_args__
    assert any(
        tuple(c.columns.keys())
        == ("provider", "competition_code", "season_year", "external_id")
        for c in (args if isinstance(args, tuple) else (args,))
    )


def test_standings_snapshot_has_rows_relationship():
    from app.models.entities import StandingsSnapshot

    assert "rows" in StandingsSnapshot.__mapper__.relationships
    cols = StandingsSnapshot.__table__.c
    assert "competition_code" in cols
    assert "season_year" in cols
    assert "pool_id" not in cols


def test_league_config_and_idempotency_models():
    from app.models.entities import DraftIdempotencyKey, League

    assert "config" in League.__table__.c
    cols = DraftIdempotencyKey.__table__.c
    assert "idempotency_key" in cols
    assert "league_id" in cols
    assert "member_id" in cols


def test_bootstrap_teams_requires_pools():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import pytest

    from app.services.bootstrap import bootstrap_teams_for_league
    from app.services.errors import ConflictError

    db = MagicMock()
    out = MagicMock()
    out.all.return_value = []
    db.scalars.return_value = out
    with pytest.raises(ConflictError) as exc:
        bootstrap_teams_for_league(
            db,
            league=SimpleNamespace(id=1),
            provider=MagicMock(),
            pool_provider_params=[],
        )
    msg = str(exc.value.message).lower()
    assert "competition" in msg or "pool" in msg


def test_bootstrap_teams_response_schema():
    from app.schemas.leagues import BootstrapTeamsResponse

    body = BootstrapTeamsResponse(
        created_teams=2, linked=5, skipped_existing=1, pools=[{"pool_key": "pl"}]
    )
    assert body.created_teams == 2
    assert body.linked == 5
    assert body.skipped_existing == 1


def test_find_idempotent_pick_returns_none_without_row():
    from unittest.mock import MagicMock

    from app.services.draft import find_idempotent_pick

    db = MagicMock()
    out = MagicMock()
    out.first.return_value = None
    db.scalars.return_value = out
    assert (
        find_idempotent_pick(db, league_id=1, member_id=2, idempotency_key="abc") is None
    )


def test_find_idempotent_pick_returns_pick():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.draft import find_idempotent_pick

    pick = SimpleNamespace(id=99)
    row = SimpleNamespace(pick_id=99)
    db = MagicMock()
    out = MagicMock()
    out.first.return_value = row
    db.scalars.return_value = out
    db.get.return_value = pick
    assert find_idempotent_pick(db, league_id=1, member_id=2, idempotency_key="abc") is pick
