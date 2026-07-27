"""Manual bonus presentation helpers shared by league reads and admin."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BonusType, ManualBonus, Match, Team
from app.schemas.leagues import BonusAwardRow


def bonus_target(bonus: ManualBonus) -> str:
    if bonus.member_id is not None:
        return "manager"
    if bonus.match_id is not None:
        return "match"
    return "team"


def match_label(match: Match, teams: dict[int, Team]) -> str:
    home = teams.get(match.home_team_id)
    away = teams.get(match.away_team_id)
    home_name = home.name if home else "Home"
    away_name = away.name if away else "Away"
    label = f"{home_name} vs {away_name}"
    if match.scheduled_matchweek is not None:
        label = f"{label} · MW{match.scheduled_matchweek}"
    return label


def load_bonus_context(
    db: Session,
    league_id: int,
    bonuses: list[ManualBonus],
    *,
    known_teams: dict[int, Team] | None = None,
) -> tuple[dict[int, BonusType], dict[int, Team], dict[int, Match]]:
    bonus_types = {
        bt.id: bt
        for bt in db.scalars(select(BonusType).where(BonusType.league_id == league_id)).all()
    }
    match_ids = {b.match_id for b in bonuses if b.match_id is not None}
    matches = {
        m.id: m
        for m in db.scalars(select(Match).where(Match.id.in_(match_ids or [0]))).all()
    }
    team_ids = {b.team_id for b in bonuses if b.team_id is not None}
    for match in matches.values():
        team_ids.add(match.home_team_id)
        team_ids.add(match.away_team_id)
    teams = dict(known_teams or {})
    missing = team_ids - set(teams)
    if missing:
        for t in db.scalars(select(Team).where(Team.id.in_(missing))).all():
            teams[t.id] = t
    return bonus_types, teams, matches


def bonus_award_row(
    bonus: ManualBonus,
    *,
    bonus_types: dict[int, BonusType],
    teams: dict[int, Team],
    matches: dict[int, Match],
) -> BonusAwardRow:
    bt = bonus_types.get(bonus.bonus_type_id)
    key = bt.key if bt else "bonus"
    label = (bt.label or bt.key) if bt else "bonus"
    team = teams.get(bonus.team_id) if bonus.team_id is not None else None
    match = matches.get(bonus.match_id) if bonus.match_id is not None else None
    return BonusAwardRow(
        id=bonus.public_id,
        target=bonus_target(bonus),
        team_id=team.public_id if team else None,
        team_name=team.name if team else None,
        crest_url=team.crest_url if team else None,
        match_id=match.public_id if match else None,
        match_label=match_label(match, teams) if match else None,
        scheduled_matchweek=match.scheduled_matchweek if match else None,
        bonus_type=key,
        bonus_type_label=label,
        points=float(bonus.points),
        reason=bonus.notes,
        awarded_at=bonus.created_at,
    )
