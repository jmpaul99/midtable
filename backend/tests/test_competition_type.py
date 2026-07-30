"""football-data.org competition.type parsing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.providers.football_data import FootballDataProvider
from app.services.bootstrap import attach_template_structure
from app.services.competitions import default_competition_type_for_code


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


def test_default_competition_type_for_code():
    assert default_competition_type_for_code("PL") == "LEAGUE"
    assert default_competition_type_for_code("ELC") == "LEAGUE"
    assert default_competition_type_for_code("CL") == "CUP"
    assert default_competition_type_for_code("WC") == "CUP"
    assert default_competition_type_for_code("UNKNOWN") is None


def test_attach_template_structure_sets_competition_type():
    added: list[object] = []
    db = MagicMock()
    db.add.side_effect = lambda obj: added.append(obj)
    template = SimpleNamespace(
        pool_definitions=[
            {
                "key": "premier_league",
                "label": "Premier League",
                "competition_code": "PL",
                "season_year": 2026,
                "slot_count": 5,
            },
            {
                "key": "ucl",
                "label": "Champions League",
                "competition_code": "CL",
                "season_year": 2026,
                "slot_count": 1,
                "competition_type": "CUP",
            },
        ],
        bonus_types=[],
    )
    attach_template_structure(
        db, league=SimpleNamespace(id=1), template=template
    )
    pools = [obj for obj in added if getattr(obj, "key", None)]
    by_key = {p.key: p for p in pools}
    assert by_key["premier_league"].competition_type == "LEAGUE"
    assert by_key["ucl"].competition_type == "CUP"
