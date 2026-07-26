import logging
import re
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth.jwt import AuthenticatedUser, get_current_profile, get_current_user
from app.db import get_db
from app.deps import is_platform_admin
from app.models import CompetitionTemplate, League, LeagueMember, Profile
from app.schemas.templates import (
    RecentTemplateUsage,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])

_STAFF_FLAG_KEYS = frozenset({"featured", "made_by_staff"})
_RECENT_LIMIT = 8
_KEY_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify_template_key(label: str) -> str:
    slug = _KEY_SLUG_RE.sub("_", label.strip().lower()).strip("_")
    return (slug[:48] or "template").rstrip("_")


def _allocate_template_key(db: Session, label: str) -> str:
    base = _slugify_template_key(label)
    for _ in range(12):
        candidate = f"{base}_{uuid.uuid4().hex[:8]}"
        exists = db.scalars(
            select(CompetitionTemplate).where(CompetitionTemplate.key == candidate)
        ).first()
        if exists is None:
            return candidate
    return f"template_{uuid.uuid4().hex}"


def _can_edit_template(
    row: CompetitionTemplate,
    *,
    profile: Profile,
    user: AuthenticatedUser,
) -> bool:
    if is_platform_admin(profile, user):
        return True
    return (
        row.created_by_profile_id is not None
        and row.created_by_profile_id == profile.id
    )


def _template_response(
    row: CompetitionTemplate,
    *,
    profile: Profile,
    user: AuthenticatedUser,
) -> TemplateResponse:
    created_by_id = row.created_by.public_id if row.created_by is not None else None
    base = TemplateResponse.model_validate(row)
    return base.model_copy(
        update={
            "created_by_id": created_by_id,
            "can_edit": _can_edit_template(row, profile=profile, user=user),
        }
    )


def _require_template_editor(
    row: CompetitionTemplate,
    *,
    profile: Profile,
    user: AuthenticatedUser,
) -> None:
    if _can_edit_template(row, profile=profile, user=user):
        return
    logger.warning(
        "authz denied reason=not_template_owner template_id=%s profile_id=%s",
        row.public_id,
        profile.public_id,
    )
    raise HTTPException(
        status_code=403,
        detail="Only the template creator can edit this template. Copy it to make changes.",
    )


@router.get("/templates", response_model=list[TemplateResponse])
def list_templates(
    profile: Profile = Depends(get_current_profile),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TemplateResponse]:
    rows = db.scalars(
        select(CompetitionTemplate).options(joinedload(CompetitionTemplate.created_by))
    ).unique().all()
    return [_template_response(row, profile=profile, user=user) for row in rows]


@router.get("/templates/recent", response_model=list[RecentTemplateUsage])
def list_recent_templates(
    profile: Profile = Depends(get_current_profile),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RecentTemplateUsage]:
    rows = db.execute(
        select(League, CompetitionTemplate)
        .join(LeagueMember, LeagueMember.league_id == League.id)
        .join(CompetitionTemplate, CompetitionTemplate.id == League.template_id)
        .options(joinedload(CompetitionTemplate.created_by))
        .where(
            LeagueMember.profile_id == profile.id,
            League.template_id.is_not(None),
        )
        .order_by(League.created_at.desc())
        .limit(_RECENT_LIMIT)
    ).unique().all()
    return [
        RecentTemplateUsage(
            template=_template_response(template, profile=profile, user=user),
            league_id=league.public_id,
            league_name=league.name,
            used_at=league.created_at,
        )
        for league, template in rows
    ]


@router.post("/templates", response_model=TemplateResponse, status_code=201)
def create_template(
    payload: TemplateCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> TemplateResponse:
    data = payload.model_dump()
    if not is_platform_admin(profile, user):
        data["featured"] = False
        data["made_by_staff"] = False
    data["key"] = _allocate_template_key(db, payload.label)
    row = CompetitionTemplate(**data, created_by_profile_id=profile.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    row = db.scalars(
        select(CompetitionTemplate)
        .where(CompetitionTemplate.id == row.id)
        .options(joinedload(CompetitionTemplate.created_by))
    ).unique().one()
    logger.info(
        "template created template_id=%s key=%s creator_profile_id=%s",
        row.public_id,
        row.key,
        profile.public_id,
    )
    return _template_response(row, profile=profile, user=user)


@router.get("/templates/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: UUID,
    profile: Profile = Depends(get_current_profile),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TemplateResponse:
    row = db.scalars(
        select(CompetitionTemplate)
        .where(CompetitionTemplate.public_id == template_id)
        .options(joinedload(CompetitionTemplate.created_by))
    ).unique().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_response(row, profile=profile, user=user)


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: UUID,
    payload: TemplateUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> TemplateResponse:
    row = db.scalars(
        select(CompetitionTemplate)
        .where(CompetitionTemplate.public_id == template_id)
        .options(joinedload(CompetitionTemplate.created_by))
    ).unique().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    _require_template_editor(row, profile=profile, user=user)
    updates = payload.model_dump(exclude_unset=True)
    if not is_platform_admin(profile, user):
        for key in _STAFF_FLAG_KEYS:
            updates.pop(key, None)
    for key, value in updates.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    row = db.scalars(
        select(CompetitionTemplate)
        .where(CompetitionTemplate.id == row.id)
        .options(joinedload(CompetitionTemplate.created_by))
    ).unique().one()
    logger.info("template updated template_id=%s key=%s", row.public_id, row.key)
    return _template_response(row, profile=profile, user=user)


@router.post("/templates/{template_id}/duplicate", response_model=TemplateResponse, status_code=201)
def duplicate_template(
    template_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> TemplateResponse:
    source = db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.public_id == template_id)
    ).first()
    if source is None:
        raise HTTPException(status_code=404, detail="Template not found")
    copy_label = f"{source.label} (copy)"
    row = CompetitionTemplate(
        key=_allocate_template_key(db, copy_label),
        label=copy_label,
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
        roster_club_order=source.roster_club_order or "draft",
        max_members=source.max_members,
        featured=False,
        made_by_staff=False,
        created_by_profile_id=profile.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    row = db.scalars(
        select(CompetitionTemplate)
        .where(CompetitionTemplate.id == row.id)
        .options(joinedload(CompetitionTemplate.created_by))
    ).unique().one()
    logger.info(
        "template duplicated source_id=%s template_id=%s key=%s creator_profile_id=%s",
        source.public_id,
        row.public_id,
        row.key,
        profile.public_id,
    )
    return _template_response(row, profile=profile, user=user)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(
    template_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> None:
    row = db.scalars(
        select(CompetitionTemplate).where(CompetitionTemplate.public_id == template_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    _require_template_editor(row, profile=profile, user=user)
    logger.info("template deleted template_id=%s key=%s", row.public_id, row.key)
    db.delete(row)
    db.commit()
