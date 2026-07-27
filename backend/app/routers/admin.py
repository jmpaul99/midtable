import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import require_commissioner, require_league_member, team_in_league
from app.logging_config import log_id
from app.models import (
    BonusType,
    League,
    LeagueMember,
    ManualBonus,
    Match,
    Profile,
    RosterEntry,
    Team,
)
from app.schemas.admin import BonusTypeCreate, BonusTypeUpdate, ManualBonusCreate
from app.services.match_queries import pool_for_match
from app.services.members import member_label

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


@router.get("/leagues/{league_id}/bonus-types")
def list_bonus_types(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    rows = db.scalars(select(BonusType).where(BonusType.league_id == league.id)).all()
    return [
        {
            "id": str(row.public_id),
            "key": row.key,
            "label": row.label,
            "default_points": float(row.default_points),
            "sort_order": row.sort_order,
            "include_in_phases": row.include_in_phases,
        }
        for row in rows
    ]


@router.post("/leagues/{league_id}/bonus-types", status_code=201)
def create_bonus_type(
    payload: BonusTypeCreate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    row = BonusType(
        league_id=league.id,
        key=payload.key,
        label=payload.label,
        default_points=payload.default_points,
        sort_order=payload.sort_order,
        include_in_phases=payload.include_in_phases or [],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "bonus type created league_id=%s bonus_type_id=%s key=%s default_points=%s",
        log_id(league),
        row.public_id,
        row.key,
        float(row.default_points),
    )
    return {"id": str(row.public_id), "key": row.key}


@router.patch("/leagues/{league_id}/bonus-types/{bonus_type_id}")
def update_bonus_type(
    bonus_type_id: UUID,
    payload: BonusTypeUpdate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    row = db.scalars(
        select(BonusType).where(
            BonusType.public_id == bonus_type_id,
            BonusType.league_id == league.id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="bonus type not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    logger.info(
        "bonus type updated league_id=%s bonus_type_id=%s key=%s changed_fields=%s",
        log_id(league),
        row.public_id,
        row.key,
        sorted(data.keys()),
    )
    return {
        "id": str(row.public_id),
        "key": row.key,
        "label": row.label,
        "default_points": float(row.default_points),
    }


@router.delete("/leagues/{league_id}/bonus-types/{bonus_type_id}", status_code=204)
def delete_bonus_type(
    bonus_type_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> None:
    league, _ = membership
    row = db.scalars(
        select(BonusType).where(
            BonusType.public_id == bonus_type_id,
            BonusType.league_id == league.id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="bonus type not found")
    in_use = db.scalars(
        select(ManualBonus).where(ManualBonus.bonus_type_id == row.id).limit(1)
    ).first()
    if in_use is not None:
        raise HTTPException(status_code=409, detail="Bonus type has awarded manuals; revoke them first")
    logger.warning(
        "bonus type deleted league_id=%s bonus_type_id=%s key=%s",
        log_id(league),
        row.public_id,
        row.key,
    )
    db.delete(row)
    db.commit()


def _bonus_target(row: ManualBonus) -> str:
    if row.member_id is not None:
        return "manager"
    if row.match_id is not None:
        return "match"
    return "team"


def _match_label(match: Match, teams: dict[int, Team]) -> str:
    home = teams.get(match.home_team_id)
    away = teams.get(match.away_team_id)
    home_name = home.name if home else "Home"
    away_name = away.name if away else "Away"
    label = f"{home_name} vs {away_name}"
    if match.scheduled_matchweek is not None:
        label = f"{label} · MW{match.scheduled_matchweek}"
    return label


@router.get("/leagues/{league_id}/manual-bonuses")
def list_manual_bonuses(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> list[dict]:
    league, _ = membership
    rows = db.scalars(select(ManualBonus).where(ManualBonus.league_id == league.id)).all()
    types = {
        b.id: b
        for b in db.scalars(select(BonusType).where(BonusType.league_id == league.id)).all()
    }
    team_ids = {r.team_id for r in rows if r.team_id is not None}
    match_ids = {r.match_id for r in rows if r.match_id is not None}
    matches = {
        m.id: m
        for m in db.scalars(select(Match).where(Match.id.in_(match_ids or [0]))).all()
    }
    for match in matches.values():
        team_ids.add(match.home_team_id)
        team_ids.add(match.away_team_id)
    teams = {
        t.id: t
        for t in db.scalars(select(Team).where(Team.id.in_(team_ids or [0]))).all()
    }
    roster = {
        r.team_id: r
        for r in db.scalars(select(RosterEntry).where(RosterEntry.league_id == league.id)).all()
    }
    members = {
        m.id: m
        for m in db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    }
    out = []
    for row in rows:
        target = _bonus_target(row)
        team = teams.get(row.team_id) if row.team_id is not None else None
        match = matches.get(row.match_id) if row.match_id is not None else None
        btype = types.get(row.bonus_type_id)
        if target == "manager":
            member = members.get(row.member_id) if row.member_id is not None else None
        else:
            entry = roster.get(row.team_id) if row.team_id is not None else None
            member = members.get(entry.member_id) if entry else None
        profile = db.get(Profile, member.profile_id) if member else None
        out.append(
            {
                "id": str(row.public_id),
                "target": target,
                "team_id": str(team.public_id) if team else None,
                "team_name": team.name if team else None,
                "match_id": str(match.public_id) if match else None,
                "match_label": _match_label(match, teams) if match else None,
                "member_id": str(member.public_id) if member else None,
                "display_name": member_label(member, profile) if member else None,
                "bonus_type": btype.key if btype else None,
                "points": float(row.points),
                "reason": row.notes,
                "awarded_at": row.created_at.isoformat() if row.created_at else None,
                "revoked_at": None,
            }
        )
    return out


@router.post("/leagues/{league_id}/manual-bonuses", status_code=201)
def award_manual_bonus(
    payload: ManualBonusCreate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    bonus_type = db.scalars(
        select(BonusType).where(
            BonusType.public_id == payload.bonus_type_id,
            BonusType.league_id == league.id,
        )
    ).first()
    if bonus_type is None:
        raise HTTPException(status_code=404, detail="bonus type not found")

    team: Team | None = None
    match: Match | None = None
    member: LeagueMember | None = None

    if payload.target in ("team", "match"):
        assert payload.team_id is not None
        team = team_in_league(db, league.id, payload.team_id)

    if payload.target == "match":
        assert payload.match_id is not None
        match = db.scalars(select(Match).where(Match.public_id == payload.match_id)).first()
        if match is None or pool_for_match(db, league, match) is None:
            raise HTTPException(status_code=404, detail="match not found")
        assert team is not None
        if team.id not in (match.home_team_id, match.away_team_id):
            raise HTTPException(
                status_code=400,
                detail="team must be home or away in the selected match",
            )

    if payload.target == "manager":
        assert payload.member_id is not None
        member = db.scalars(
            select(LeagueMember).where(
                LeagueMember.public_id == payload.member_id,
                LeagueMember.league_id == league.id,
            )
        ).first()
        if member is None:
            raise HTTPException(status_code=404, detail="manager not found")

    points = payload.points if payload.points is not None else Decimal(bonus_type.default_points)
    row = ManualBonus(
        league_id=league.id,
        team_id=team.id if team else None,
        match_id=match.id if match else None,
        member_id=member.id if member else None,
        bonus_type_id=bonus_type.id,
        points=points,
        notes=payload.notes,
        created_by_profile_id=profile.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "manual bonus awarded league_id=%s bonus_id=%s target=%s team_id=%s match_id=%s "
        "member_id=%s bonus_type=%s points=%s actor_profile_id=%s",
        league.public_id,
        row.public_id,
        payload.target,
        team.public_id if team else None,
        match.public_id if match else None,
        member.public_id if member else None,
        bonus_type.key,
        float(points),
        profile.public_id,
    )
    return {"id": str(row.public_id), "points": float(row.points), "target": payload.target}


@router.delete("/leagues/{league_id}/manual-bonuses/{bonus_id}", status_code=204)
def revoke_manual_bonus(
    bonus_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> None:
    league, actor = membership
    row = db.scalars(
        select(ManualBonus).where(
            ManualBonus.public_id == bonus_id,
            ManualBonus.league_id == league.id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Manual bonus not found")
    logger.info(
        "manual bonus revoked league_id=%s bonus_id=%s points=%s actor=%s",
        league.public_id,
        row.public_id,
        float(row.points),
        actor.public_id,
    )
    db.delete(row)
    db.commit()
