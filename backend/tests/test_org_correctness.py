"""Additional tests for draft idempotency edges, bootstrap gates, recompute seeds."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.draft import find_idempotent_pick
from app.services.errors import ConflictError


def test_find_idempotent_pick_null_pick_id_conflicts():
    db = MagicMock()
    out = MagicMock()
    out.first.return_value = SimpleNamespace(pick_id=None)
    db.scalars.return_value = out
    with pytest.raises(ConflictError):
        find_idempotent_pick(db, league_id=1, member_id=2, idempotency_key="k")


def test_prior_leagues_blocking_empty_without_template():
    from app.services.bootstrap import prior_leagues_blocking

    db = MagicMock()
    out = MagicMock()
    out.first.return_value = None
    db.scalars.return_value = out
    assert prior_leagues_blocking(db, template_key="missing") == []


def test_recompute_seeds_one_per_pool():
    """Document expected seed selection: earliest finished per scoring pool."""
    finished = [
        SimpleNamespace(pool_id=1, kickoff_at=2, id=10),
        SimpleNamespace(pool_id=1, kickoff_at=1, id=11),
        SimpleNamespace(pool_id=2, kickoff_at=5, id=20),
    ]
    by_pool: dict[int, list] = {}
    for m in finished:
        by_pool.setdefault(m.pool_id, []).append(m)
    seeds = []
    for pool_matches in by_pool.values():
        pool_matches.sort(key=lambda x: x.kickoff_at)
        seeds.append(pool_matches[0])
    assert {s.id for s in seeds} == {11, 20}


def test_match_to_input_adapter():
    from datetime import UTC, datetime

    from app.services.match_adapters import match_to_input

    match = SimpleNamespace(
        id=1,
        pool_id=2,
        home_team_id=3,
        away_team_id=4,
        kickoff_at=datetime(2026, 8, 1, tzinfo=UTC),
        home_goals=1,
        away_goals=0,
        status="FINISHED",
        scheduled_matchweek=1,
        stage=None,
    )
    mi = match_to_input(match)
    assert mi.match_id == 1
    assert mi.home_goals == 1
