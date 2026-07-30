"""League CRUD + settings."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import require_commissioner, require_league_member
from app.models import (
    CompetitionTemplate,
    DraftState,
    League,
    LeagueMember,
    PoolTeam,
    Profile,
    RosterEntry,
    TeamPool,
)
from app.routers.league_mappers import (
    _league_detail,
    _league_response,
    _member_response,
)
from app.schemas.leagues import (
    LeagueCreate,
    LeagueDetailResponse,
    LeagueResponse,
    LeagueSettingsUpdate,
    MemberAdminUpdate,
    MemberResponse,
    MemberSelfUpdate,
)
from app.services.bootstrap import attach_template_structure
from app.services.members import (
    default_team_name,
    is_sole_commissioner,
    renumber_draft_slots,
)
from app.logging_config import log_id
from app.services import analytics as analytics_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["leagues"])


def _league_list_sort_key(league: League) -> tuple[bool, bool, datetime]:
    """Drafting first, then other non-complete; newest created first within a group (reverse=True)."""
    created = league.created_at or datetime.min.replace(tzinfo=UTC)
    return (league.status == "drafting", league.status != "complete", created)


def _league_config_from_template(
    template: CompetitionTemplate | None,
    *,
    max_members: int | None,
) -> dict:
    config: dict = {"max_members": max_members}
    if template is None:
        return config
    order = template.roster_club_order
    config["roster_club_order"] = order if order in ("draft", "competition") else "draft"
    return config


def _my_standing(
    db: Session, league: League, membership: LeagueMember
) -> tuple[int | None, int, float | None, bool]:
    """Return (rank, member_count, points, has_scored) for the current membership."""
    try:
        entries = analytics_service.leaderboard(db, league, phase_key=None)
    except ValueError as exc:
        logger.warning(
            "leaderboard unavailable for standing league_id=%s error=%s",
            log_id(league),
            exc,
        )
        members = db.scalars(
            select(LeagueMember).where(LeagueMember.league_id == league.id)
        ).all()
        return None, len(members), None, False
    member_key = str(membership.public_id)
    mine = next((row for row in entries if row.get("member_id") == member_key), None)
    rank = int(mine["rank"]) if mine and mine.get("rank") is not None else None
    points = float(mine["total_points"]) if mine and mine.get("total_points") is not None else None
    has_scored = any(float(row.get("total_points") or 0) > 0 for row in entries)
    return rank, len(entries), points, has_scored


@router.get("/leagues", response_model=list[LeagueResponse])
def list_leagues(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> list[LeagueResponse]:
    memberships = db.scalars(
        select(LeagueMember).where(LeagueMember.profile_id == profile.id)
    ).all()
    league_ids = [m.league_id for m in memberships]
    if not league_ids:
        return []
    by_league = {m.league_id: m for m in memberships}
    leagues = sorted(
        db.scalars(select(League).where(League.id.in_(league_ids))).all(),
        key=_league_list_sort_key,
        reverse=True,
    )
    rows: list[LeagueResponse] = []
    for league in leagues:
        membership = by_league[league.id]
        my_rank, member_count, my_points, has_scored = _my_standing(db, league, membership)
        rows.append(
            _league_response(
                league,
                role="commissioner" if membership.is_commissioner else "member",
                my_rank=my_rank,
                member_count=member_count,
                my_points=my_points,
                my_draft_slot=membership.draft_slot,
                has_scored=has_scored,
            )
        )
    return rows


@router.post("/leagues", response_model=LeagueDetailResponse)
def create_league(
    payload: LeagueCreate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> LeagueDetailResponse:
    template = None
    if payload.template_id:
        template = db.scalars(
            select(CompetitionTemplate).where(
                CompetitionTemplate.public_id == payload.template_id
            )
        ).first()
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
    league = League(
        template_id=template.id if template else None,
        name=payload.name,
        season_label=payload.season_label,
        draft_style=payload.draft_style if not template else template.draft_style,
        preassign_mode=payload.preassign_mode if not template else template.preassign_mode,
        preassign_count=(
            payload.preassign_count if not template else template.preassign_count
        ),
        result_points=(template.result_points if template else {"win": 3, "draw": 1}),
        upset_rules=(template.upset_rules if template else {}),
        leaderboard_phases=(template.leaderboard_phases if template else []),
        leaderboard_tiebreaks=(
            template.leaderboard_tiebreaks
            if template
            else [{"metric": "total_points", "direction": "desc"}]
        ),
        buy_in=(template.buy_in if template else 0),
        payouts=(template.payouts if template else []),
        config=_league_config_from_template(template, max_members=payload.max_members),
        draft_scheduled_at=payload.draft_scheduled_at,
        pick_timer_seconds=payload.pick_timer_seconds,
    )
    db.add(league)
    db.flush()
    member = LeagueMember(
        league_id=league.id,
        profile_id=profile.id,
        is_commissioner=True,
        draft_slot=1,
        team_name=default_team_name(profile.display_name),
    )
    db.add(member)
    if template:
        attach_template_structure(db, league=league, template=template)
    else:
        db.add(DraftState(league_id=league.id, current_pick_number=1, status="pending"))
    db.commit()
    db.refresh(league)
    db.refresh(member)
    logger.info(
        "league created league_id=%s name=%s template_id=%s creator_profile_id=%s",
        log_id(league),
        league.name,
        payload.template_id,
        log_id(profile),
    )
    return _league_detail(db, league, member)


@router.get("/leagues/{league_id}", response_model=LeagueDetailResponse)
def get_league(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> LeagueDetailResponse:
    league, member = membership
    return _league_detail(db, league, member)


@router.get("/leagues/{league_id}/members", response_model=list[MemberResponse])
def list_members(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[MemberResponse]:
    league, _ = membership
    members = db.scalars(
        select(LeagueMember).where(LeagueMember.league_id == league.id)
    ).all()
    return [_member_response(m, db.get(Profile, m.profile_id)) for m in members]


@router.patch("/leagues/{league_id}/members/me", response_model=MemberResponse)
def update_my_membership(
    payload: MemberSelfUpdate,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> MemberResponse:
    """Update the current user's fantasy team name in this league."""
    league, member = membership
    data = payload.model_dump(exclude_unset=True)
    if "team_name" in data:
        member.team_name = data["team_name"]
        logger.info(
            "member team_name updated league_id=%s member_id=%s",
            log_id(league),
            log_id(member),
        )
    db.commit()
    db.refresh(member)
    return _member_response(member, db.get(Profile, member.profile_id))


@router.patch("/leagues/{league_id}/members/{member_id}", response_model=MemberResponse)
def update_member(
    member_id: UUID,
    payload: MemberAdminUpdate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> MemberResponse:
    """Appoint or demote a commissioner on an existing membership."""
    league, actor = membership
    members = list(
        db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    )
    target = next((m for m in members if m.public_id == member_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Manager not found")
    if not payload.is_commissioner and is_sole_commissioner(target, members):
        raise HTTPException(
            status_code=409,
            detail="Cannot demote the last commissioner",
        )
    target.is_commissioner = payload.is_commissioner
    db.commit()
    db.refresh(target)
    logger.info(
        "member commissioner updated league_id=%s actor=%s target=%s is_commissioner=%s",
        log_id(league),
        log_id(actor),
        log_id(target),
        payload.is_commissioner,
    )
    return _member_response(target, db.get(Profile, target.profile_id))


@router.delete(
    "/leagues/{league_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    member_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> Response:
    """Remove a manager before the draft opens."""
    league, actor = membership
    if league.status != "pre_draft":
        raise HTTPException(
            status_code=409,
            detail="Managers can only be removed before the draft opens",
        )
    members = list(
        db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    )
    target = next((m for m in members if m.public_id == member_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Manager not found")
    if target.id == actor.id and is_sole_commissioner(target, members):
        raise HTTPException(
            status_code=409,
            detail="Cannot remove the last commissioner",
        )
    remaining = [m for m in members if m.id != target.id]
    logger.warning(
        "member removed league_id=%s actor=%s target=%s",
        log_id(league),
        log_id(actor),
        log_id(target),
    )
    db.delete(target)
    db.flush()
    renumber_draft_slots(db, remaining)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/leagues/{league_id}/settings", response_model=LeagueDetailResponse)
def update_settings(
    payload: LeagueSettingsUpdate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> LeagueDetailResponse:
    league, member = membership
    data = payload.model_dump(exclude_unset=True)
    max_members = data.pop("max_members", None)
    roster_club_order = data.pop("roster_club_order", None)
    pools_patch = data.pop("pools", None)
    remove_pool_ids = data.pop("remove_pool_ids", None)
    draft_style = data.get("draft_style")
    preassign_mode = data.get("preassign_mode")
    preassign_count = data.get("preassign_count")
    if (
        draft_style is not None or preassign_mode is not None or preassign_count is not None
    ) and league.status != "pre_draft":
        raise HTTPException(
            status_code=409,
            detail="Draft style and preassign settings can only be changed before the draft opens.",
        )
    if preassign_mode is not None or preassign_count is not None:
        effective_mode = (
            preassign_mode if preassign_mode is not None else league.preassign_mode
        )
        effective_count = (
            preassign_count
            if preassign_count is not None
            else getattr(league, "preassign_count", 1)
        )
        try:
            from app.services.preassign import validate_preassign_pair

            validate_preassign_pair(effective_mode, effective_count)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if max_members is not None and league.status != "pre_draft":
        raise HTTPException(
            status_code=409,
            detail="Number of managers can only be changed before the draft opens.",
        )
    if "draft_scheduled_at" in data:
        draft_state = db.scalars(
            select(DraftState).where(DraftState.league_id == league.id)
        ).first()
        draft_open = draft_state is not None and draft_state.status in {"open", "complete"}
        if league.status != "pre_draft" or draft_open:
            raise HTTPException(
                status_code=409,
                detail="Draft schedule can only be changed before the draft opens.",
            )
    if "pick_timer_seconds" in data and league.status == "complete":
        raise HTTPException(
            status_code=409,
            detail="Pick timer cannot be changed after the season is complete.",
        )
    if "pick_timer_seconds" in data:
        draft_state = db.scalars(
            select(DraftState).where(DraftState.league_id == league.id)
        ).first()
        if draft_state is not None and draft_state.status == "complete":
            raise HTTPException(
                status_code=409,
                detail="Pick timer cannot be changed after the draft is complete.",
            )
        new_timer = data.get("pick_timer_seconds")
        # Clearing the timer mid-draft stops the current clock immediately.
        if new_timer is None and draft_state is not None:
            draft_state.pick_deadline_at = None
        elif (
            new_timer is not None
            and draft_state is not None
            and draft_state.status == "open"
            and new_timer != league.pick_timer_seconds
        ):
            # Enabling or changing duration: restart the clock for the current pick.
            draft_state.pick_deadline_at = datetime.now(UTC) + timedelta(
                seconds=int(new_timer)
            )
    clear_preassigns = (
        preassign_mode is not None and str(preassign_mode).lower() == "off"
    )
    for key, value in data.items():
        setattr(league, key, value)
    if clear_preassigns:
        for entry in db.scalars(
            select(RosterEntry).where(
                RosterEntry.league_id == league.id,
                RosterEntry.source == "preassigned",
            )
        ).all():
            db.delete(entry)
        db.flush()
        logger.info(
            "preassigns cleared league_id=%s reason=preassign_mode_off",
            log_id(league),
        )
    if max_members is not None or roster_club_order is not None:
        config = dict(league.config or {})
        if max_members is not None:
            config["max_members"] = max_members
        if roster_club_order is not None:
            config["roster_club_order"] = roster_club_order
        league.config = config

    creating = bool(
        pools_patch
        and any(item.get("id") is None for item in pools_patch)
    )
    removing = bool(remove_pool_ids)
    if creating or removing:
        if league.status != "pre_draft":
            raise HTTPException(
                status_code=409,
                detail="Competitions can only be added or removed before the draft opens.",
            )

    if remove_pool_ids:
        for pool_public_id in remove_pool_ids:
            pool = db.scalars(
                select(TeamPool).where(
                    TeamPool.public_id == pool_public_id,
                    TeamPool.league_id == league.id,
                )
            ).first()
            if pool is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Competition not found: {pool_public_id}",
                )
            db.delete(pool)
        db.flush()

    if pools_patch is not None:
        member_count = len(
            list(db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all())
        )
        cfg_max = (league.config or {}).get("max_members")
        try:
            configured_max = int(cfg_max) if cfg_max is not None else None
        except (TypeError, ValueError):
            configured_max = None
        manager_capacity = max(member_count, configured_max or 0, 1)

        existing_pools = list(
            db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all()
        )
        keys_in_use = {p.key for p in existing_pools}
        codes_in_use = {
            (p.competition_code or "").upper()
            for p in existing_pools
            if p.competition_code
        }

        for item in pools_patch:
            pool_id = item.get("id")
            if pool_id is None:
                key = item["key"]
                code = item["competition_code"]
                if key in keys_in_use:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Competition key already in use: {key}",
                    )
                if code in codes_in_use:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Competition already added: {code}",
                    )
                pool = TeamPool(
                    league_id=league.id,
                    key=key,
                    label=item["label"],
                    scores_match_results=bool(item.get("scores_match_results", True)),
                    slot_count=int(item["slot_count"]),
                    sort_order=int(item.get("sort_order") or 0),
                    tie_break_order=["points", "gd", "gf", "name"],
                    provider=item.get("provider") or "football-data.org",
                    competition_code=code,
                    season_year=int(item["season_year"]),
                )
                db.add(pool)
                keys_in_use.add(key)
                codes_in_use.add(code)
                continue

            pool = db.scalars(
                select(TeamPool).where(
                    TeamPool.public_id == pool_id,
                    TeamPool.league_id == league.id,
                )
            ).first()
            if pool is None:
                raise HTTPException(status_code=404, detail=f"Competition not found: {pool_id}")
            if "sort_order" in item and item["sort_order"] is not None:
                pool.sort_order = int(item["sort_order"])
            if "label" in item and item["label"] is not None:
                pool.label = item["label"]
            if "scores_match_results" in item and item["scores_match_results"] is not None:
                pool.scores_match_results = bool(item["scores_match_results"])

            structural_locked = league.status != "pre_draft"
            if structural_locked:
                if (
                    "provider" in item
                    and item["provider"] is not None
                    and item["provider"] != pool.provider
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Competition provider can only be changed before the draft opens.",
                    )
                if (
                    "competition_code" in item
                    and item["competition_code"] is not None
                    and (item["competition_code"] or "").upper()
                    != (pool.competition_code or "").upper()
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Competition can only be changed before the draft opens.",
                    )
                if (
                    "season_year" in item
                    and item["season_year"] is not None
                    and int(item["season_year"]) != int(pool.season_year or 0)
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Season year can only be changed before the draft opens.",
                    )
                if (
                    "slot_count" in item
                    and item["slot_count"] is not None
                    and int(item["slot_count"]) != int(pool.slot_count)
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Roster slots can only be changed before the draft opens.",
                    )

            if "provider" in item and item["provider"] is not None:
                pool.provider = item["provider"]
            if "competition_code" in item and item["competition_code"] is not None:
                new_code = item["competition_code"]
                old_code = (pool.competition_code or "").upper()
                if new_code != old_code and new_code in codes_in_use:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Competition already added: {new_code}",
                    )
                if old_code:
                    codes_in_use.discard(old_code)
                pool.competition_code = new_code
                pool.competition_type = None
                codes_in_use.add(new_code)
            if "season_year" in item and item["season_year"] is not None:
                pool.season_year = int(item["season_year"])
            if "slot_count" in item and item["slot_count"] is not None:
                new_slots = int(item["slot_count"])
                team_count = len(
                    list(db.scalars(select(PoolTeam).where(PoolTeam.pool_id == pool.id)).all())
                )
                needed = new_slots * manager_capacity
                if team_count > 0 and needed > team_count:
                    label = pool.label or pool.key
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"{label}: {new_slots} roster slots × {manager_capacity} managers "
                            f"needs {needed} clubs, but only {team_count} are loaded. "
                            "Lower slots, reduce max managers, or load more clubs."
                        ),
                    )
                pool.slot_count = new_slots
    db.commit()
    db.refresh(league)
    changed_keys = sorted(payload.model_dump(exclude_unset=True).keys())
    logger.info(
        "league settings updated league_id=%s actor=%s changed_keys=%s "
        "pools_creating=%s pools_removing=%s",
        log_id(league),
        log_id(member),
        changed_keys,
        creating,
        removing,
    )
    return _league_detail(db, league, member)


@router.post("/leagues/{league_id}/complete", response_model=LeagueDetailResponse)
def complete_league(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> LeagueDetailResponse:
    """Mark a league season as complete (no longer open for scoring / prior-season gates)."""
    league, member = membership
    if league.status == "complete":
        raise HTTPException(status_code=409, detail="League is already complete")
    prior = league.status
    league.status = "complete"
    db.commit()
    db.refresh(league)
    logger.info(
        "league completed league_id=%s prior_status=%s actor=%s",
        log_id(league),
        prior,
        log_id(member),
    )
    return _league_detail(db, league, member)


@router.delete(
    "/leagues/{league_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_league(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> Response:
    """Permanently delete a league and cascaded season data."""
    league, member = membership
    logger.warning(
        "league deleted league_id=%s name=%s status=%s actor=%s",
        log_id(league),
        getattr(league, "name", "?"),
        getattr(league, "status", "?"),
        log_id(member),
    )
    db.delete(league)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

