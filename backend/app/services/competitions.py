"""Curated football-data.org free-plan competitions."""

from __future__ import annotations

from typing import Literal, TypedDict

TeamKind = Literal["national_men", "national_women", "club"]


class AvailableCompetition(TypedDict):
    code: str
    label: str
    key: str
    team_kind: TeamKind


# Codes available on the football-data.org free plan.
AVAILABLE_COMPETITIONS: tuple[AvailableCompetition, ...] = (
    {
        "code": "WC",
        "label": "FIFA World Cup",
        "key": "fifa_world_cup",
        "team_kind": "national_men",
    },
    {
        "code": "CL",
        "label": "UEFA Champions League",
        "key": "uefa_champions_league",
        "team_kind": "club",
    },
    {"code": "BL1", "label": "Bundesliga", "key": "bundesliga", "team_kind": "club"},
    {"code": "DED", "label": "Eredivisie", "key": "eredivisie", "team_kind": "club"},
    {
        "code": "BSA",
        "label": "Campeonato Brasileiro Série A",
        "key": "campeonato_brasileiro_serie_a",
        "team_kind": "club",
    },
    {
        "code": "PD",
        "label": "Primera Division",
        "key": "primera_division",
        "team_kind": "club",
    },
    {"code": "FL1", "label": "Ligue 1", "key": "ligue_1", "team_kind": "club"},
    {"code": "ELC", "label": "Championship", "key": "championship", "team_kind": "club"},
    {
        "code": "PPL",
        "label": "Primeira Liga",
        "key": "primeira_liga",
        "team_kind": "club",
    },
    {
        "code": "EC",
        "label": "European Championship",
        "key": "european_championship",
        "team_kind": "national_men",
    },
    {"code": "SA", "label": "Serie A", "key": "serie_a", "team_kind": "club"},
    {
        "code": "PL",
        "label": "Premier League",
        "key": "premier_league",
        "team_kind": "club",
    },
)

AVAILABLE_COMPETITION_CODES: frozenset[str] = frozenset(
    c["code"] for c in AVAILABLE_COMPETITIONS
)

_TEAM_KIND_BY_CODE: dict[str, TeamKind] = {
    c["code"]: c["team_kind"] for c in AVAILABLE_COMPETITIONS
}

_NATIONAL_KINDS: frozenset[str] = frozenset({"national_men", "national_women"})


def normalize_competition_code(code: str | None) -> str | None:
    if code is None:
        return None
    trimmed = code.strip().upper()
    return trimmed or None


def is_allowed_competition_code(code: str | None) -> bool:
    normalized = normalize_competition_code(code)
    if normalized is None:
        return False
    return normalized in AVAILABLE_COMPETITION_CODES


def team_kind_for_competition(code: str | None) -> TeamKind | None:
    normalized = normalize_competition_code(code)
    if normalized is None:
        return None
    return _TEAM_KIND_BY_CODE.get(normalized)


def national_competition_codes(kind: TeamKind | None = None) -> frozenset[str]:
    if kind is None:
        return frozenset(
            c["code"] for c in AVAILABLE_COMPETITIONS if c["team_kind"] in _NATIONAL_KINDS
        )
    return frozenset(c["code"] for c in AVAILABLE_COMPETITIONS if c["team_kind"] == kind)


def should_apply_team_kind(current: str | None, incoming: TeamKind) -> bool:
    """National kinds win over club; never downgrade national → club."""
    if current == incoming:
        return False
    if current in _NATIONAL_KINDS and incoming == "club":
        return False
    return True
