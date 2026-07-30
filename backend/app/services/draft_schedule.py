"""Validation for league draft_scheduled_at."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import League, Match
from app.services.errors import DomainError
from app.services.match_queries import (
    CompetitionKey,
    competition_key_predicate,
    competition_keys_from_pools,
    scoring_pools_for_league,
)

logger = logging.getLogger(__name__)


def aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def earliest_kickoff_for_keys(
    db: Session,
    keys: list[CompetitionKey],
) -> datetime | None:
    """Return the earliest match kickoff across the given competition keys."""
    if not keys:
        return None
    normalized: list[CompetitionKey] = [
        (provider, competition_code.upper(), int(season_year))
        for provider, competition_code, season_year in keys
        if competition_code
    ]
    predicate = competition_key_predicate(normalized)
    if predicate is None:
        return None
    value = db.scalar(select(func.min(Match.kickoff_at)).where(predicate))
    return aware(value) if value is not None else None


def earliest_kickoff_for_league(db: Session, league: League) -> datetime | None:
    pools = scoring_pools_for_league(db, league)
    return earliest_kickoff_for_keys(db, competition_keys_from_pools(pools))


def draft_schedule_after_first_kickoff(db: Session, league: League) -> bool:
    """True when a scheduled draft would open on/after the first competition match."""
    if league.draft_scheduled_at is None:
        return False
    first_kickoff = earliest_kickoff_for_league(db, league)
    if first_kickoff is None:
        return False
    return aware(league.draft_scheduled_at) >= first_kickoff


def clear_draft_schedule_if_after_first_kickoff(db: Session, league: League) -> bool:
    """Clear an invalid pre-draft schedule once fixtures make the kickoff known."""
    if league.status != "pre_draft" or not draft_schedule_after_first_kickoff(db, league):
        return False
    logger.warning(
        "clearing draft_scheduled_at league_id=%s scheduled_at=%s reason=after_first_kickoff",
        getattr(league, "public_id", league.id),
        league.draft_scheduled_at,
    )
    league.draft_scheduled_at = None
    return True


def validate_draft_scheduled_at(
    db: Session,
    scheduled_at: datetime | None,
    *,
    competition_keys: list[CompetitionKey] | None = None,
    league: League | None = None,
    now: datetime | None = None,
) -> None:
    """Reject schedules in the past or on/after the first competition match.

    ``None`` clears the schedule and is always allowed. When no fixtures are
    loaded yet, only the past-date rule is enforced.
    """
    if scheduled_at is None:
        return

    when = aware(scheduled_at)
    current = aware(now or datetime.now(UTC))
    if when <= current:
        raise DomainError("Draft start must be in the future.")

    keys = list(competition_keys or [])
    if not keys and league is not None:
        keys = competition_keys_from_pools(scoring_pools_for_league(db, league))

    first_kickoff = earliest_kickoff_for_keys(db, keys) if keys else None
    if first_kickoff is not None and when >= first_kickoff:
        raise DomainError(
            "Draft start must be before the first match of the competition."
        )
