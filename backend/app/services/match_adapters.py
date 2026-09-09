"""ORM Match → scoring MatchInput adapter (leaf module)."""

from __future__ import annotations

from app.models import Match
from app.services.scoring import MatchInput


def match_to_input(match: Match, *, pool_id: int) -> MatchInput:
    raw_status = getattr(match, "status", None) or "SCHEDULED"
    # Normalize so is_finished / FINISHED_STATUSES checks are not case-sensitive.
    # Provider payloads are usually upper-case, but a mixed-case status would
    # update Match rows while leaving scoring and gap-fill gated off.
    status = str(raw_status).upper()
    return MatchInput(
        match_id=match.id,
        pool_id=pool_id,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        kickoff_at=match.kickoff_at,
        home_goals=match.home_goals,
        away_goals=match.away_goals,
        status=status,
        duration=getattr(match, "duration", None) or "REGULAR",
        scheduled_matchweek=match.scheduled_matchweek,
        stage=match.stage,
    )
