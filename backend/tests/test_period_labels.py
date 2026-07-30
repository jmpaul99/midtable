"""Period labels and hybrid stage/matchday catalogs."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.period_labels import (
    build_period_catalog,
    events_by_competition_type,
    expanded_stages,
    format_period_range,
    format_period_short,
    period_kind,
    points_by_period_from_events,
    resolve_period_key,
    scoring_competition_type,
)


def test_period_kind_league_vs_cup():
    assert period_kind("LEAGUE") == "matchweek"
    assert period_kind("CUP") == "round"
    assert period_kind("LEAGUE_CUP") == "round"
    assert period_kind(None) == "round"


def test_format_period_short_and_range():
    assert format_period_short(3, "LEAGUE") == "MW3"
    assert format_period_short(3, "CUP") == "R3"
    assert format_period_range(1, 19, "LEAGUE") == "Matchweeks 1–19"
    assert format_period_range(1, 3, "CUP") == "Rounds 1–3"


def test_scoring_competition_type_prefers_scoring_pool():
    pools = [
        SimpleNamespace(
            scores_match_results=False,
            competition_type="LEAGUE",
            sort_order=1,
            id=1,
        ),
        SimpleNamespace(
            scores_match_results=True,
            competition_type="CUP",
            sort_order=2,
            id=2,
        ),
    ]
    assert scoring_competition_type(pools) == "CUP"


def test_events_use_period_labels_for_their_match_competition_type():
    pools = [
        SimpleNamespace(
            id=1,
            sort_order=1,
            scores_match_results=True,
            competition_code="PL",
            competition_type="LEAGUE",
        ),
        SimpleNamespace(
            id=2,
            sort_order=2,
            scores_match_results=True,
            competition_code="CL",
            competition_type="CUP",
        ),
    ]
    matches = {
        10: SimpleNamespace(id=10, competition_code="PL"),
        20: SimpleNamespace(id=20, competition_code="CL"),
    }
    events = [
        SimpleNamespace(match_id=10, stage="REGULAR_SEASON", scheduled_matchweek=1),
        SimpleNamespace(match_id=10, stage="REGULAR_SEASON", scheduled_matchweek=2),
        SimpleNamespace(match_id=20, stage="GROUP_STAGE", scheduled_matchweek=1),
        SimpleNamespace(match_id=20, stage="GROUP_STAGE", scheduled_matchweek=2),
    ]

    grouped = events_by_competition_type(events, matches, pools)
    catalogs = {
        competition_type: build_period_catalog(
            [(event.stage, event.scheduled_matchweek) for event in grouped_events],
            competition_type=competition_type,
        )
        for competition_type, grouped_events in grouped
    }

    assert [competition_type for competition_type, _ in grouped] == ["LEAGUE", "CUP"]
    assert [(p.key, p.label) for p in catalogs["LEAGUE"]] == [
        ("REGULAR_SEASON:1", "MW1"),
        ("REGULAR_SEASON:2", "MW2"),
    ]
    assert [(p.key, p.label) for p in catalogs["CUP"]] == [
        ("GROUP_STAGE:1", "Group stage · R1"),
        ("GROUP_STAGE:2", "Group stage · R2"),
    ]


def test_wc_style_catalog_expands_group_collapses_knockout():
    items = [
        ("GROUP_STAGE", 1),
        ("GROUP_STAGE", 2),
        ("GROUP_STAGE", 3),
        ("LAST_16", 1),
        ("QUARTER_FINALS", 1),
        ("SEMI_FINALS", None),
        ("FINAL", 1),
    ]
    catalog = build_period_catalog(items, competition_type="CUP")
    keys = [p.key for p in catalog]
    assert keys == [
        "FINAL",
        "SEMI_FINALS",
        "QUARTER_FINALS",
        "LAST_16",
        "GROUP_STAGE:1",
        "GROUP_STAGE:2",
        "GROUP_STAGE:3",
    ]
    by_key = {p.key: p for p in catalog}
    assert by_key["GROUP_STAGE:2"].label == "Group stage · R2"
    assert by_key["FINAL"].label == "Final"
    assert by_key["LAST_16"].label == "Round of 16"
    assert by_key["SEMI_FINALS"].scheduled_matchweek is None

    expanded = expanded_stages(catalog)
    assert "GROUP_STAGE" in expanded
    assert "FINAL" not in expanded
    assert resolve_period_key("GROUP_STAGE", 2, expanded=expanded) == "GROUP_STAGE:2"
    assert resolve_period_key("FINAL", 1, expanded=expanded) == "FINAL"


def test_expanded_stage_null_matchweek_keeps_stage_bucket():
    items = [
        ("GROUP_STAGE", 1),
        ("GROUP_STAGE", 2),
        ("GROUP_STAGE", None),
        ("FINAL", 1),
    ]
    catalog = build_period_catalog(items, competition_type="CUP")
    keys = [p.key for p in catalog]
    assert "GROUP_STAGE:1" in keys
    assert "GROUP_STAGE:2" in keys
    assert "GROUP_STAGE" in keys
    assert "FINAL" in keys

    expanded = expanded_stages(catalog)
    assert resolve_period_key("GROUP_STAGE", None, expanded=expanded) == "GROUP_STAGE"
    assert resolve_period_key("GROUP_STAGE", 1, expanded=expanded) == "GROUP_STAGE:1"

    events = [
        SimpleNamespace(stage="GROUP_STAGE", scheduled_matchweek=1, points=3),
        SimpleNamespace(stage="GROUP_STAGE", scheduled_matchweek=2, points=1),
        SimpleNamespace(stage="GROUP_STAGE", scheduled_matchweek=None, points=2),
        SimpleNamespace(stage="FINAL", scheduled_matchweek=1, points=6),
    ]
    rows = points_by_period_from_events(events, competition_type="CUP")
    by_key = {r["period_key"]: r for r in rows}
    assert by_key["GROUP_STAGE:1"]["points"] == 3.0
    assert by_key["GROUP_STAGE:2"]["points"] == 1.0
    assert by_key["GROUP_STAGE"]["points"] == 2.0
    assert by_key["FINAL"]["points"] == 6.0


def test_pl_style_catalog_uses_matchweek_labels():
    items = [("REGULAR_SEASON", n) for n in range(1, 5)]
    catalog = build_period_catalog(items, competition_type="LEAGUE")
    assert [p.key for p in catalog] == [
        "REGULAR_SEASON:1",
        "REGULAR_SEASON:2",
        "REGULAR_SEASON:3",
        "REGULAR_SEASON:4",
    ]
    assert catalog[0].label == "MW1"
    assert "Regular season" not in catalog[0].label


def test_league_catalog_merges_null_stage_into_regular_season():
    events = [
        SimpleNamespace(stage="REGULAR_SEASON", scheduled_matchweek=1, points=3),
        SimpleNamespace(stage=None, scheduled_matchweek=1, points=1),
        SimpleNamespace(stage="", scheduled_matchweek=2, points=2),
        SimpleNamespace(stage="REGULAR_SEASON", scheduled_matchweek=2, points=3),
    ]

    rows = points_by_period_from_events(events, competition_type="LEAGUE")
    by_key = {row["period_key"]: row for row in rows}

    assert set(by_key) == {"REGULAR_SEASON:1", "REGULAR_SEASON:2"}
    assert by_key["REGULAR_SEASON:1"]["points"] == 4.0
    assert by_key["REGULAR_SEASON:2"]["points"] == 5.0
    assert resolve_period_key(
        None, 2, expanded=frozenset({"REGULAR_SEASON"})
    ) == "REGULAR_SEASON:2"


def test_points_by_period_from_events_wc():
    events = [
        SimpleNamespace(stage="GROUP_STAGE", scheduled_matchweek=1, points=3),
        SimpleNamespace(stage="GROUP_STAGE", scheduled_matchweek=1, points=1),
        SimpleNamespace(stage="GROUP_STAGE", scheduled_matchweek=2, points=3),
        SimpleNamespace(stage="FINAL", scheduled_matchweek=1, points=6),
    ]
    rows = points_by_period_from_events(events, competition_type="CUP")
    by_key = {r["period_key"]: r for r in rows}
    assert by_key["GROUP_STAGE:1"]["points"] == 4.0
    assert by_key["GROUP_STAGE:2"]["points"] == 3.0
    assert by_key["FINAL"]["points"] == 6.0
    assert by_key["FINAL"]["label"] == "Final"
