import logging
import re
import uuid
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, case, cast, func, literal_column, or_, select, text
from sqlalchemy.orm import Session, joinedload

from app.auth.jwt import AuthenticatedUser, get_current_profile, get_current_user
from app.db import get_db
from app.deps import is_platform_admin
from app.models import CompetitionTemplate, League, LeagueMember, Profile
from app.routers.leagues_core import _league_config_from_template
from app.schemas.templates import (
    RecentTemplateUsage,
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.preassign import effective_preassign_count

logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])

_STAFF_FLAG_KEYS = frozenset({"featured", "made_by_staff"})
_TEMPLATE_SYNC_FIELDS = (
    "result_points",
    "upset_rules",
    "leaderboard_phases",
    "leaderboard_tiebreaks",
    "buy_in",
    "payouts",
    "draft_style",
    "preassign_mode",
    "preassign_count",
)
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


NumericCompareOp = Literal["eq", "min", "max"]


def _roster_slot_count_expr():
    return literal_column(
        "(SELECT COALESCE(SUM((e->>'count')::int), 0)"
        " FROM jsonb_array_elements(competition_templates.roster_slots) AS e)"
    )


def _bonus_count_expr():
    return func.coalesce(func.jsonb_array_length(CompetitionTemplate.bonus_types), 0)


def _upsets_enabled_expr():
    return CompetitionTemplate.upset_rules["enabled"].astext


def _apply_numeric_compare(column, value: int, op: NumericCompareOp):
    if op == "min":
        return column >= value
    if op == "max":
        return column <= value
    return column == value


def _distinct_competition_codes(db: Session) -> list[str]:
    rows = db.execute(
        text(
            """
            SELECT DISTINCT UPPER(TRIM(e->>'competition_code')) AS code
            FROM competition_templates,
                 jsonb_array_elements(pool_definitions) AS e
            WHERE NULLIF(TRIM(e->>'competition_code'), '') IS NOT NULL
            ORDER BY code
            """
        )
    ).all()
    return [str(row.code) for row in rows if row.code]


@router.get("/templates", response_model=TemplateListResponse)
def list_templates(
    profile: Profile = Depends(get_current_profile),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=48),
    featured: bool | None = Query(default=None),
    made_by_staff: bool | None = Query(default=None),
    competition: list[str] | None = Query(default=None),
    members: int | None = Query(default=None, ge=1, le=100),
    members_op: NumericCompareOp = Query(default="eq"),
    roster: int | None = Query(default=None, ge=0, le=100),
    roster_op: NumericCompareOp = Query(default="eq"),
    upsets: bool | None = Query(default=None),
    bonuses: bool | None = Query(default=None),
) -> TemplateListResponse:
    filters = []
    if featured is not None:
        filters.append(CompetitionTemplate.featured.is_(featured))
    if made_by_staff is not None:
        filters.append(CompetitionTemplate.made_by_staff.is_(made_by_staff))

    for code in competition or []:
        normalized = code.strip().upper()
        if not normalized:
            continue
        filters.append(
            CompetitionTemplate.pool_definitions.contains(
                [{"competition_code": normalized}]
            )
        )

    if members is not None:
        if members_op == "min":
            # Unlimited (null) can host at least N members.
            filters.append(
                or_(
                    CompetitionTemplate.max_members.is_(None),
                    CompetitionTemplate.max_members >= members,
                )
            )
        elif members_op == "max":
            filters.append(CompetitionTemplate.max_members.is_not(None))
            filters.append(CompetitionTemplate.max_members <= members)
        else:
            filters.append(CompetitionTemplate.max_members == members)

    if roster is not None:
        roster_sum = _roster_slot_count_expr()
        filters.append(_apply_numeric_compare(roster_sum, roster, roster_op))

    if upsets is True:
        filters.append(_upsets_enabled_expr() == "true")
    elif upsets is False:
        filters.append(_upsets_enabled_expr().is_distinct_from("true"))

    bonus_count = _bonus_count_expr()
    if bonuses is True:
        filters.append(bonus_count > 0)
    elif bonuses is False:
        filters.append(bonus_count == 0)

    query_text = (q or "").strip()
    if query_text:
        pattern = f"%{query_text}%"
        filters.append(
            or_(
                CompetitionTemplate.label.ilike(pattern),
                CompetitionTemplate.key.ilike(pattern),
                cast(CompetitionTemplate.pool_definitions, String).ilike(pattern),
                cast(CompetitionTemplate.leaderboard_phases, String).ilike(pattern),
                cast(CompetitionTemplate.roster_slots, String).ilike(pattern),
            )
        )

    count_stmt = select(func.count()).select_from(CompetitionTemplate)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = int(db.scalar(count_stmt) or 0)

    stmt = select(CompetitionTemplate).options(
        joinedload(CompetitionTemplate.created_by)
    )
    if filters:
        stmt = stmt.where(*filters)

    if query_text:
        prefix = f"{query_text}%"
        contains = f"%{query_text}%"
        relevance = case(
            (CompetitionTemplate.label.ilike(prefix), 0),
            (CompetitionTemplate.label.ilike(contains), 1),
            (
                cast(CompetitionTemplate.pool_definitions, String).ilike(contains),
                2,
            ),
            else_=3,
        )
        stmt = stmt.order_by(relevance.asc(), CompetitionTemplate.label.asc())
    else:
        stmt = stmt.order_by(
            CompetitionTemplate.featured.desc(),
            CompetitionTemplate.label.asc(),
        )

    offset = (page - 1) * page_size
    rows = db.scalars(stmt.offset(offset).limit(page_size)).unique().all()
    return TemplateListResponse(
        items=[_template_response(row, profile=profile, user=user) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        competition_codes=_distinct_competition_codes(db),
    )


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
    if "preassign_mode" in updates or "preassign_count" in updates:
        from app.services.preassign import validate_preassign_pair

        effective_mode = updates.get("preassign_mode", row.preassign_mode)
        effective_count = updates.get(
            "preassign_count", getattr(row, "preassign_count", 1)
        )
        try:
            validate_preassign_pair(effective_mode, effective_count)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    for key, value in updates.items():
        setattr(row, key, value)
    leagues_updated = 0
    if updates:
        pre_draft_leagues = db.scalars(
            select(League).where(
                League.template_id == row.id,
                League.status == "pre_draft",
            )
        ).all()
        for league in pre_draft_leagues:
            for field in _TEMPLATE_SYNC_FIELDS:
                setattr(league, field, getattr(row, field))
            max_members = (league.config or {}).get("max_members")
            league.config = _league_config_from_template(row, max_members=max_members)
            leagues_updated += 1
    db.commit()
    db.refresh(row)
    row = db.scalars(
        select(CompetitionTemplate)
        .where(CompetitionTemplate.id == row.id)
        .options(joinedload(CompetitionTemplate.created_by))
    ).unique().one()
    logger.info(
        "template updated template_id=%s key=%s pre_draft_leagues_synced=%s",
        row.public_id,
        row.key,
        leagues_updated,
    )
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
        preassign_count=effective_preassign_count(getattr(source, "preassign_count", None)),
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
