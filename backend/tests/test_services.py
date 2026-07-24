from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException

from football_draft_league.providers.football_data import FootballDataProvider
from football_draft_league.schemas import RankingImport
from football_draft_league.services import (
    _draft_member,
    attribute_points_by_current_owner,
    parse_ranking_rows,
    phase_completeness,
    split_payouts,
    team_available,
)


def test_linear_and_snake_draft_turns() -> None:
    order = ["a", "b", "c"]
    assert [_draft_member(order, pick, "linear")[0] for pick in range(1, 7)] == [
        "a",
        "b",
        "c",
        "a",
        "b",
        "c",
    ]
    assert [_draft_member(order, pick, "snake")[0] for pick in range(1, 7)] == [
        "a",
        "b",
        "c",
        "c",
        "b",
        "a",
    ]


def test_ranking_import_handles_csv_and_pasted_lines() -> None:
    csv_payload = RankingImport(
        member_id=UUID(int=1),
        text="rank,team\n2,Arsenal\n1,Liverpool",
        has_header=True,
        team_column=1,
        rank_column=0,
    )
    assert parse_ranking_rows(csv_payload) == [(2, "Arsenal"), (1, "Liverpool")]

    pasted = RankingImport(member_id=UUID(int=1), text="Arsenal\nLiverpool")
    assert parse_ranking_rows(pasted) == [(1, "Arsenal"), (2, "Liverpool")]


def test_ranking_import_rejects_duplicate_ranks() -> None:
    payload = RankingImport(
        member_id=UUID(int=1),
        text="1,Arsenal\n1,Liverpool",
        team_column=1,
        rank_column=0,
    )
    with pytest.raises(HTTPException):
        parse_ranking_rows(payload)


def test_tied_payouts_split_occupied_places() -> None:
    first = UUID(int=1)
    tied_a = UUID(int=2)
    tied_b = UUID(int=3)
    payouts = [
        {"rank": 1, "amount": "100"},
        {"rank": 2, "amount": "60"},
        {"rank": 3, "amount": "30"},
    ]
    result = split_payouts([(1, first), (2, tied_a), (2, tied_b)], payouts)
    assert result[first] == Decimal("100")
    assert result[tied_a] == Decimal("45")
    assert result[tied_b] == Decimal("45")


def test_team_availability_follows_current_owner() -> None:
    assert team_available(None) is True
    assert team_available({"member_id": str(UUID(int=1))}) is False


def test_points_reattribute_when_current_owner_changes() -> None:
    team = UUID(int=10)
    original_owner = UUID(int=1)
    corrected_owner = UUID(int=2)
    points = {team: Decimal("17")}

    assert attribute_points_by_current_owner(points, {team: original_owner}) == {
        original_owner: Decimal("17")
    }
    assert attribute_points_by_current_owner(points, {team: corrected_owner}) == {
        corrected_owner: Decimal("17")
    }


def test_phase_completeness_supports_matchweeks_and_stages() -> None:
    matches = [
        {"matchday": 1, "stage": "REGULAR_SEASON", "status": "finished"},
        {"matchday": 2, "stage": "REGULAR_SEASON", "status": "scheduled"},
        {"matchday": None, "stage": "FINAL", "status": "finished"},
    ]
    first_two = phase_completeness(
        {"key": "opening", "name": "Opening", "matchweek_range": [1, 2]},
        matches,
    )
    assert first_two["matching_matches"] == 2
    assert first_two["remaining_matches"] == 1
    assert first_two["is_final"] is False

    final = phase_completeness(
        {"key": "final", "name": "Final", "stage_in": ["FINAL"]}, matches
    )
    assert final["matching_matches"] == 1
    assert final["is_final"] is True


def test_provider_preserves_zero_rate_limit_remaining() -> None:
    rate = FootballDataProvider._rate_limit(
        httpx.Headers(
            {
                "x-requests-remaining": "0",
                "x-requests-available-minute": "10",
            }
        )
    )
    assert rate.remaining == 0
