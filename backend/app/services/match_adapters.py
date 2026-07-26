"""ORM Match → scoring MatchInput adapter (leaf module)."""

from __future__ import annotations

from app.models import Match
from app.services.scoring import MatchInput


def match_to_input(match: Match) -> MatchInput:
    return MatchInput(
        match_id=match.id,
        pool_id=match.pool_id,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        kickoff_at=match.kickoff_at,
        home_goals=match.home_goals,
        away_goals=match.away_goals,
        status=match.status,
        duration=getattr(match, "duration", None) or "REGULAR",
        scheduled_matchweek=match.scheduled_matchweek,
        stage=match.stage,
    )
