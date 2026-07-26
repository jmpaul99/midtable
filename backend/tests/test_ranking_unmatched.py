"""FIFA unmatched = national competition teams missing a ranking link."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.competitions import (
    national_competition_codes,
    should_apply_team_kind,
    team_kind_for_competition,
)
from app.services.ranking_catalog import (
    candidate_teams_for_catalog,
    match_team_for_entry,
    unmatched_for_catalog,
)


def _team(
    *,
    tid: int,
    external_id: str,
    name: str,
    tla: str | None = None,
    team_kind: str | None = None,
    short_name: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=tid,
        provider="football-data.org",
        external_id=external_id,
        name=name,
        short_name=short_name,
        tla=tla,
        team_kind=team_kind,
    )


def _entry(
    *,
    rank: int,
    team_name: str,
    country_code: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        rank=rank,
        team_name=team_name,
        country_code=country_code,
    )


def test_competition_team_kinds():
    assert team_kind_for_competition("WC") == "national_men"
    assert team_kind_for_competition("EC") == "national_men"
    assert team_kind_for_competition("PL") == "club"
    assert team_kind_for_competition("cl") == "club"
    assert "WC" in national_competition_codes("national_men")
    assert "PL" not in national_competition_codes()


def test_national_team_kind_not_downgraded_to_club():
    assert should_apply_team_kind("national_men", "club") is False
    assert should_apply_team_kind("club", "national_men") is True
    assert should_apply_team_kind(None, "club") is True
    assert should_apply_team_kind("national_men", "national_men") is False


def test_fifa_men_candidates_exclude_clubs_with_same_tla():
    nation = _team(
        tid=2,
        external_id="7657",
        name="Portugal",
        tla="POR",
        team_kind="national_men",
    )
    entry = _entry(rank=6, team_name="Portugal", country_code="POR")
    assert (
        match_team_for_entry(
            entry,
            [nation],
            overrides_by_code={},
            overrides_by_name={},
        )
        is nation
    )

    catalog = SimpleNamespace(key="fifa_men")
    db = MagicMock()
    db.scalars.return_value.all.return_value = [nation]
    teams = candidate_teams_for_catalog(db, catalog)
    assert teams == [nation]
    assert all(t.team_kind == "national_men" for t in teams)


def test_unmatched_ignores_fifa_only_nations():
    """FIFA countries outside the tournament are not unmatched."""
    france = _team(
        tid=1,
        external_id="773",
        name="France",
        tla="FRA",
        team_kind="national_men",
    )
    # San Marino is in FIFA catalog but not in national team set.
    entries = [
        _entry(rank=1, team_name="France", country_code="FRA"),
        _entry(rank=180, team_name="San Marino", country_code="SMR"),
    ]
    catalog = SimpleNamespace(id=1, key="fifa_men")

    def _scalars(stmt):  # noqa: ARG001
        out = MagicMock()
        text = str(stmt)
        if "ranking_catalog_team_overrides" in text.lower() or "RankingCatalogTeamOverride" in text:
            out.all.return_value = []
        elif "RankingCatalogEntry" in text or "ranking_catalog_entries" in text.lower():
            out.all.return_value = entries
        else:
            out.all.return_value = [france]
        return out

    db = MagicMock()
    db.scalars.side_effect = _scalars

    with patch(
        "app.services.ranking_catalog.candidate_teams_for_catalog",
        return_value=[france],
    ):
        rows = unmatched_for_catalog(db, catalog)

    assert len(rows) == 0


def test_unmatched_includes_national_team_without_fifa_match():
    mystery = _team(
        tid=9,
        external_id="9999",
        name="Mystery Nation",
        tla="MYS",
        team_kind="national_men",
    )
    entries = [
        _entry(rank=1, team_name="France", country_code="FRA"),
    ]
    catalog = SimpleNamespace(id=1, key="fifa_men")
    db = MagicMock()

    with patch(
        "app.services.ranking_catalog.candidate_teams_for_catalog",
        return_value=[mystery],
    ):
        # Provide entries/overrides via scalars
        def _scalars(stmt):  # noqa: ARG001
            out = MagicMock()
            # First call entries, second overrides (order in unmatched_for_catalog)
            return out

        calls: list[MagicMock] = []

        def scalars_side_effect(stmt):  # noqa: ARG001
            out = MagicMock()
            if len(calls) == 0:
                out.all.return_value = entries
            else:
                out.all.return_value = []
            calls.append(out)
            return out

        db.scalars.side_effect = scalars_side_effect
        rows = unmatched_for_catalog(db, catalog)

    assert len(rows) == 1
    assert rows[0]["external_team_id"] == "9999"
    assert rows[0]["team_name"] == "Mystery Nation"


def test_unmatched_excludes_clubs():
    club = _team(
        tid=3,
        external_id="64",
        name="Porto",
        tla="POR",
        team_kind="club",
    )
    entries = [_entry(rank=6, team_name="Portugal", country_code="POR")]
    catalog = SimpleNamespace(id=1, key="fifa_men")
    db = MagicMock()

    with patch(
        "app.services.ranking_catalog.candidate_teams_for_catalog",
        return_value=[],  # clubs filtered out of candidates
    ):
        calls = {"n": 0}

        def scalars_side_effect(stmt):  # noqa: ARG001
            out = MagicMock()
            if calls["n"] == 0:
                out.all.return_value = entries
            else:
                out.all.return_value = []
            calls["n"] += 1
            return out

        db.scalars.side_effect = scalars_side_effect
        rows = unmatched_for_catalog(db, catalog)

    assert rows == []
    assert club.team_kind == "club"


def test_candidate_teams_league_filters_by_kind():
    france = _team(
        tid=1, external_id="1", name="France", tla="FRA", team_kind="national_men"
    )
    arsenal = _team(
        tid=2, external_id="57", name="Arsenal", tla="ARS", team_kind="club"
    )
    catalog = SimpleNamespace(key="fifa_men")
    league = SimpleNamespace(id=10)
    db = MagicMock()

    with patch(
        "app.services.ranking_catalog.league_pool_teams",
        return_value=[france, arsenal],
    ):
        teams = candidate_teams_for_catalog(db, catalog, sample_league=league)

    assert teams == [france]
