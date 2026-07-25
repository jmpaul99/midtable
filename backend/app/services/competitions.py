"""Curated football-data.org free-plan competitions."""

from __future__ import annotations

from typing import TypedDict


class AvailableCompetition(TypedDict):
    code: str
    label: str
    key: str


# Codes available on the football-data.org free plan.
AVAILABLE_COMPETITIONS: tuple[AvailableCompetition, ...] = (
    {"code": "WC", "label": "FIFA World Cup", "key": "fifa_world_cup"},
    {"code": "CL", "label": "UEFA Champions League", "key": "uefa_champions_league"},
    {"code": "BL1", "label": "Bundesliga", "key": "bundesliga"},
    {"code": "DED", "label": "Eredivisie", "key": "eredivisie"},
    {
        "code": "BSA",
        "label": "Campeonato Brasileiro Série A",
        "key": "campeonato_brasileiro_serie_a",
    },
    {"code": "PD", "label": "Primera Division", "key": "primera_division"},
    {"code": "FL1", "label": "Ligue 1", "key": "ligue_1"},
    {"code": "ELC", "label": "Championship", "key": "championship"},
    {"code": "PPL", "label": "Primeira Liga", "key": "primeira_liga"},
    {"code": "EC", "label": "European Championship", "key": "european_championship"},
    {"code": "SA", "label": "Serie A", "key": "serie_a"},
    {"code": "PL", "label": "Premier League", "key": "premier_league"},
)

AVAILABLE_COMPETITION_CODES: frozenset[str] = frozenset(
    c["code"] for c in AVAILABLE_COMPETITIONS
)


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
