import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import require_platform_admin
from app.models import CompetitionTemplate, Profile
from app.schemas.templates import TemplateCreate, TemplateResponse, TemplateUpdate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])


@router.get("/templates", response_model=list[TemplateResponse])
def list_templates(
    _: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> list[TemplateResponse]:
    rows = db.scalars(select(CompetitionTemplate)).all()
    return [TemplateResponse.model_validate(row) for row in rows]


@router.post("/templates", response_model=TemplateResponse, status_code=201)
def create_template(
    payload: TemplateCreate,
    _: object = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> TemplateResponse:
    existing = db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.key == payload.key)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Template key already exists")
    row = CompetitionTemplate(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("template created template_id=%s key=%s", row.public_id, row.key)
    return TemplateResponse.model_validate(row)


@router.get("/templates/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: UUID,
    _: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> TemplateResponse:
    row = db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.public_id == template_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateResponse.model_validate(row)


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: UUID,
    payload: TemplateUpdate,
    _: object = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> TemplateResponse:
    row = db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.public_id == template_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    logger.info("template updated template_id=%s key=%s", row.public_id, row.key)
    return TemplateResponse.model_validate(row)


@router.post("/templates/{template_id}/duplicate", response_model=TemplateResponse, status_code=201)
def duplicate_template(
    template_id: UUID,
    _: object = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> TemplateResponse:
    source = db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.public_id == template_id)
    ).first()
    if source is None:
        raise HTTPException(status_code=404, detail="Template not found")
    new_key = f"{source.key}_copy"
    suffix = 1
    while db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.key == new_key)
    ).first():
        suffix += 1
        new_key = f"{source.key}_copy{suffix}"
    row = CompetitionTemplate(
        key=new_key,
        label=f"{source.label} (copy)",
        draft_style=source.draft_style,
        preassign_mode=source.preassign_mode,
        result_points=dict(source.result_points),
        upset_rules=dict(source.upset_rules),
        leaderboard_phases=list(source.leaderboard_phases),
        leaderboard_tiebreaks=list(source.leaderboard_tiebreaks),
        buy_in=source.buy_in,
        payouts=list(source.payouts),
        roster_slots=list(source.roster_slots),
        pool_definitions=list(source.pool_definitions),
        bonus_types=list(source.bonus_types),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "template duplicated source_id=%s template_id=%s key=%s",
        source.public_id,
        row.public_id,
        row.key,
    )
    return TemplateResponse.model_validate(row)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(
    template_id: UUID,
    _: object = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> None:
    row = db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.public_id == template_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    logger.info("template deleted template_id=%s key=%s", row.public_id, row.key)
    db.delete(row)
    db.commit()
