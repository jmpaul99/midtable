from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import require_commissioner, team_in_league
from app.models import BonusType, League, LeagueMember, ManualBonus, Profile, RosterEntry, Team
from app.schemas.admin import BonusTypeCreate, BonusTypeUpdate, ManualBonusCreate
from app.services.members import member_label


router = APIRouter(tags=["admin"])


@router.get("/leagues/{league_id}/bonus-types")
def list_bonus_types(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
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
    db.delete(row)
    db.commit()


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
    teams = {
        t.id: t
        for t in db.scalars(
            select(Team).where(Team.id.in_([r.team_id for r in rows] or [0]))
        ).all()
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
        team = teams.get(row.team_id)
        btype = types.get(row.bonus_type_id)
        entry = roster.get(row.team_id)
        member = members.get(entry.member_id) if entry else None
        profile = db.get(Profile, member.profile_id) if member else None
        out.append(
            {
                "id": str(row.public_id),
                "team_id": str(team.public_id) if team else None,
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
    team = team_in_league(db, league.id, payload.team_id)
    bonus_type = db.scalars(
        select(BonusType).where(
            BonusType.public_id == payload.bonus_type_id,
            BonusType.league_id == league.id,
        )
    ).first()
    if bonus_type is None:
        raise HTTPException(status_code=404, detail="bonus type not found")
    points = payload.points if payload.points is not None else Decimal(bonus_type.default_points)
    row = ManualBonus(
        league_id=league.id,
        team_id=team.id,
        bonus_type_id=bonus_type.id,
        points=points,
        notes=payload.notes,
        created_by_profile_id=profile.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.public_id), "points": float(row.points)}


@router.delete("/leagues/{league_id}/manual-bonuses/{bonus_id}", status_code=204)
def revoke_manual_bonus(
    bonus_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> None:
    league, _ = membership
    row = db.scalars(
        select(ManualBonus).where(
            ManualBonus.public_id == bonus_id,
            ManualBonus.league_id == league.id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Manual bonus not found")
    db.delete(row)
    db.commit()
