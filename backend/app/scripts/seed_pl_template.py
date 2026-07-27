"""Insert/update the premier_league competition_template with PL defaults."""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.models import CompetitionTemplate

logger = logging.getLogger(__name__)

PL_UPSET_RULES = {
    "enabled": True,
    "rank_source": "league_table_at_kickoff",
    "eligibility": {"min_played": 8},
    "thresholds": [
        {
            "key": "minor_upset",
            "name": "Minor upset",
            "min_gap": 5,
            "max_gap": 9,
            "result": "win",
            "points": 1,
        },
        {
            "key": "major_upset",
            "name": "Major upset",
            "min_gap": 10,
            "max_gap": None,
            "result": "win",
            "points": 3,
        },
        {
            "key": "major_upset_draw",
            "name": "Major upset draw",
            "min_gap": 10,
            "max_gap": None,
            "result": "draw",
            "points": 1,
        },
    ],
}

PL_PHASES = [
    {
        "key": "mw1_19",
        "label": "Matchweeks 1–19",
        "match_filter": {"type": "matchweek_range", "from": 1, "to": 19},
        "include_bonus_types": [],
    }
]

PL_TIEBREAKS = [
    {"metric": "total_points", "direction": "desc"},
    {
        "metric": "event_points",
        "event_types": ["minor_upset", "major_upset", "major_upset_draw"],
        "direction": "desc",
    },
    {"metric": "event_count", "event_types": ["win"], "direction": "desc"},
]

PL_ROSTER_SLOTS = [
    {"pool_key": "premier_league", "count": 5, "label": "Premier League team"},
    {"pool_key": "championship", "count": 1, "label": "Championship team"},
]

PL_POOL_DEFINITIONS = [
    {
        "key": "premier_league",
        "label": "Premier League",
        "scores_match_results": True,
        "slot_count": 5,
        "sort_order": 1,
        "tie_break_order": ["points", "gd", "gf", "name"],
        "provider": "football-data.org",
        "competition_code": "PL",
        "season_year": 2026,
    },
    {
        "key": "championship",
        "label": "Championship",
        "scores_match_results": False,
        "slot_count": 1,
        "sort_order": 2,
        "tie_break_order": ["points", "gd", "gf", "name"],
        "provider": "football-data.org",
        "competition_code": "ELC",
        "season_year": 2026,
    },
]

PL_BONUS_TYPES = [
    {"key": "winners", "label": "Winner’s Bonus", "default_points": 12, "sort_order": 1},
    {"key": "cl", "label": "Champions League Qualification", "default_points": 9, "sort_order": 2},
    {
        "key": "other_euro",
        "label": "Other European Qualification",
        "default_points": 6,
        "sort_order": 3,
    },
    {
        "key": "champ_promo",
        "label": "Championship Promotion",
        "default_points": 20,
        "sort_order": 4,
    },
    {"key": "relegation", "label": "Relegation Deduction", "default_points": -10, "sort_order": 5},
]

PL_PAYOUTS = [
    {"label": "Midseason 1st", "phase": "mw1_19", "position": 1, "amount": 50},
    {"label": "Season 1st", "phase": "season", "position": 1, "amount": 100},
    {"label": "Season 2nd", "phase": "season", "position": 2, "amount": 50},
]


def seed() -> CompetitionTemplate:
    with SessionLocal() as db:
        existing = db.scalars(
            select(CompetitionTemplate).where(CompetitionTemplate.key == "premier_league")
        ).first()
        if existing is None:
            existing = CompetitionTemplate(key="premier_league", label="Premier League Draft")
            db.add(existing)

        existing.label = "Premier League Draft"
        existing.draft_style = "linear"
        existing.preassign_mode = "required"
        existing.preassign_count = 1
        existing.result_points = {"win": 3, "draw": 1}
        existing.upset_rules = PL_UPSET_RULES
        existing.leaderboard_phases = PL_PHASES
        existing.leaderboard_tiebreaks = PL_TIEBREAKS
        existing.buy_in = Decimal("50")
        existing.payouts = PL_PAYOUTS
        existing.roster_slots = PL_ROSTER_SLOTS
        existing.pool_definitions = PL_POOL_DEFINITIONS
        existing.bonus_types = PL_BONUS_TYPES
        db.commit()
        db.refresh(existing)
        logger.info(
            "Seeded competition_templates.premier_league public_id=%s",
            existing.public_id,
        )
        return existing


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
