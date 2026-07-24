from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import require_commissioner
from app.models import BonusType, League, LeagueMember, ManualBonus, Profile, Team
from app.schemas.admin import BonusTypeCreate, ManualBonusCreate

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


@router.post("/leagues/{league_id}/manual-bonuses", status_code=201)
def award_manual_bonus(
    payload: ManualBonusCreate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    team = db.scalars(select(Team).where(Team.public_id == payload.team_id)).first()
    bonus_type = db.scalars(
        select(BonusType).where(
            BonusType.public_id == payload.bonus_type_id,
            BonusType.league_id == league.id,
        )
    ).first()
    if team is None or bonus_type is None:
        raise HTTPException(status_code=404, detail="team or bonus type not found")
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
