"""football-data.org competition.type parsing."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.providers.football_data import FootballDataProvider


def test_competition_type_from_payload():
    assert FootballDataProvider._competition_type_from_payload({"type": "LEAGUE"}) == "LEAGUE"
    assert FootballDataProvider._competition_type_from_payload({"type": "cup"}) == "CUP"
    assert FootballDataProvider._competition_type_from_payload({"type": "OTHER"}) is None
    assert FootballDataProvider._competition_type_from_payload({}) is None


def test_resolve_competition_season_includes_type():
    provider = FootballDataProvider(api_token="test", client=MagicMock())
    payload = {
        "type": "CUP",
        "currentSeason": {
            "id": 1,
            "startDate": "2026-06-01",
            "endDate": "2026-07-15",
        },
        "seasons": [],
    }
    provider._get = MagicMock(return_value=(payload, MagicMock()))  # type: ignore[method-assign]
    info, _ = provider.resolve_competition_season("WC", 2026)
    assert info.available is True
    assert info.competition_type == "CUP"
    assert info.season_year == 2026
