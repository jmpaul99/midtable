import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import require_commissioner, require_league_member, team_in_league
from app.models import (
    DraftPick,
    DraftState,
    League,
    LeagueMember,
    PoolTeam,
    Profile,
    RosterEntry,
    Team,
    TeamPool,
)
from app.routers.league_mappers import _member_response
from app.schemas.draft import DraftPickRequest, DraftPickResponse, DraftStateResponse
from app.schemas.leagues import DraftOrderUpdate, MemberResponse, PreassignRequest, RosterPatchRequest
from app.services.draft import (
    find_idempotent_pick,
    make_pick,
    on_clock_member,
    open_draft,
    ordered_members,
    reassign_roster_entry,
    reset_draft,
    undo_last_pick,
)
from app.services.errors import DomainError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["draft"])


def _build_draft_state(db: Session, league: League) -> DraftStateResponse:
    state = db.scalars(select(DraftState).where(DraftState.league_id == league.id)).first()
    if state is None:
        raise HTTPException(status_code=404, detail="Draft state not found")
    members = list(
        db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    )
    on_clock_id = None
    current_round = 1
    if state.status == "open" and members:
        try:
            ordered = ordered_members(members)
            member, current_round = on_clock_member(
                draft_style=league.draft_style,
                ordered=ordered,
                pick_number=state.current_pick_number,
            )
            on_clock_id = member.public_id
        except DomainError as exc:
            logger.warning(
                "draft on-clock unresolved league_id=%s status=%s pick=%s detail=%s",
                league.public_id,
                state.status,
                state.current_pick_number,
                exc.message,
            )
            on_clock_id = None
    picks = db.scalars(
        select(DraftPick)
        .where(DraftPick.league_id == league.id)
        .order_by(DraftPick.pick_number)
    ).all()
    member_by_id = {m.id: m for m in members}
    team_ids = [p.team_id for p in picks]
    teams = {
        t.id: t
        for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()
    } if team_ids else {}
    pool_ids = {p.pool_id for p in picks}
    pools = {
        p.id: p
        for p in db.scalars(select(TeamPool).where(TeamPool.id.in_(pool_ids))).all()
    } if pool_ids else {}
    pick_rows: list[DraftPickResponse] = []
    for pick in picks:
        member = member_by_id.get(pick.member_id)
        team = teams.get(pick.team_id)
        pool = pools.get(pick.pool_id)
        pick_rows.append(
            DraftPickResponse(
                id=pick.public_id,
                pick_number=pick.pick_number,
                round_number=pick.round_number,
                member_id=member.public_id if member else UUID(int=0),
                team_id=team.public_id if team else UUID(int=0),
                pool_id=pool.public_id if pool else UUID(int=0),
                team_name=team.name if team else None,
                crest_url=team.crest_url if team else None,
            )
        )
    status = state.status
    # FE historically used "running" for open drafts
    api_status = "running" if status == "open" else status
    return DraftStateResponse(
        id=state.public_id,
        status=api_status,
        current_pick_number=state.current_pick_number,
        current_round=current_round,
        on_clock_member_id=on_clock_id,
        current_member_id=on_clock_id,
        league_status=league.status,
        version=state.current_pick_number,
        picks=pick_rows,
    )


@router.get("/leagues/{league_id}/draft", response_model=DraftStateResponse)
def get_draft_state(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> DraftStateResponse:
    league, _ = membership
    return _build_draft_state(db, league)


@router.post("/leagues/{league_id}/draft/open", response_model=DraftStateResponse)
def open_league_draft(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> DraftStateResponse:
    league, _ = membership
    open_draft(db, league)
    db.commit()
    return _build_draft_state(db, league)


@router.post("/leagues/{league_id}/draft/reset", response_model=DraftStateResponse)
def reset_league_draft(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> DraftStateResponse:
    if not get_settings().is_development:
        raise HTTPException(status_code=404, detail="Not found")
    league, _ = membership
    reset_draft(db, league)
    db.commit()
    return _build_draft_state(db, league)


@router.post("/leagues/{league_id}/draft/picks", response_model=DraftStateResponse)
def submit_pick(
    payload: DraftPickRequest,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> DraftStateResponse:
    league, member = membership
    if payload.idempotency_key:
        existing = find_idempotent_pick(
            db,
            league_id=league.id,
            member_id=member.id,
            idempotency_key=payload.idempotency_key,
        )
        if existing is not None:
            return _build_draft_state(db, league)
    if payload.expected_version is not None:
        state = db.scalars(select(DraftState).where(DraftState.league_id == league.id)).first()
        if state and payload.expected_version != state.current_pick_number:
            raise HTTPException(status_code=409, detail="Draft version conflict; refresh and retry")
    make_pick(
        db,
        league=league,
        picker_member=member,
        team_public_id=payload.team_id,
        allow_commissioner_override=member.is_commissioner,
        idempotency_key=payload.idempotency_key,
    )
    db.commit()
    return _build_draft_state(db, league)


@router.put("/leagues/{league_id}/draft-order", response_model=list[MemberResponse])
def set_draft_order(
    payload: DraftOrderUpdate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> list[MemberResponse]:
    league, _ = membership
    if league.status == "drafting":
        raise HTTPException(status_code=409, detail="Draft order locked once drafting")
    members = {
        m.public_id: m
        for m in db.scalars(
            select(LeagueMember).where(LeagueMember.league_id == league.id)
        ).all()
    }
    if set(payload.member_ids) != set(members):
        raise HTTPException(status_code=400, detail="Draft order must include every manager exactly once")
    for index, mid in enumerate(payload.member_ids, start=1):
        members[mid].draft_slot = index
    db.commit()
    logger.info(
        "draft order set league_id=%s managers=%s",
        league.public_id,
        len(payload.member_ids),
    )
    return [
        _member_response(m, db.get(Profile, m.profile_id))
        for m in sorted(members.values(), key=lambda row: row.draft_slot or 0)
    ]


@router.post("/leagues/{league_id}/preassigns", status_code=201)
def preassign_team(
    payload: PreassignRequest,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    if league.status != "pre_draft":
        raise HTTPException(
            status_code=409,
            detail="Preassign only allowed before the draft opens",
        )
    if (league.preassign_mode or "none").lower() == "none":
        raise HTTPException(
            status_code=409,
            detail="Preassign is disabled for this league",
        )
    member = db.scalars(
        select(LeagueMember).where(
            LeagueMember.public_id == payload.member_id,
            LeagueMember.league_id == league.id,
        )
    ).first()
    pool = db.scalars(
        select(TeamPool).where(
            TeamPool.public_id == payload.pool_id,
            TeamPool.league_id == league.id,
        )
    ).first()
    if not member or not pool:
        raise HTTPException(status_code=404, detail="Manager or pool not found")
    team = team_in_league(db, league.id, payload.team_id)
    in_pool = db.scalars(
        select(PoolTeam).where(PoolTeam.pool_id == pool.id, PoolTeam.team_id == team.id)
    ).first()
    if in_pool is None:
        raise HTTPException(status_code=400, detail="Team is not in the selected pool")
    existing = db.scalars(
        select(RosterEntry).where(
            RosterEntry.league_id == league.id,
            RosterEntry.team_id == team.id,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Team already assigned")
    entry = RosterEntry(
        league_id=league.id,
        member_id=member.id,
        team_id=team.id,
        pool_id=pool.id,
        source="preassigned",
    )
    db.add(entry)
    db.commit()
    logger.info(
        "preassign created league_id=%s member_id=%s team_id=%s pool_id=%s",
        league.public_id,
        member.public_id,
        team.public_id,
        pool.public_id,
    )
    return {"id": str(entry.public_id)}


@router.delete("/leagues/{league_id}/draft/picks/last")
def undo_last_draft_pick(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    try:
        pick = undo_last_pick(db, league)
        team = db.get(Team, pick.team_id)
        db.commit()
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "undone_pick_number": pick.pick_number,
        "team_id": str(team.public_id) if team else None,
    }


@router.patch("/leagues/{league_id}/rosters/{entry_id}")
def patch_roster_entry(
    entry_id: UUID,
    payload: RosterPatchRequest,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    entry = db.scalars(
        select(RosterEntry).where(
            RosterEntry.public_id == entry_id,
            RosterEntry.league_id == league.id,
        )
    ).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Roster entry not found")
    new_member = None
    new_team = None
    if payload.member_id:
        new_member = db.scalars(
            select(LeagueMember).where(
                LeagueMember.public_id == payload.member_id,
                LeagueMember.league_id == league.id,
            )
        ).first()
        if new_member is None:
            raise HTTPException(status_code=404, detail="Manager not found")
    if payload.team_id:
        new_team = team_in_league(db, league.id, payload.team_id)
    try:
        reassign_roster_entry(
            db, league, entry=entry, new_member=new_member, new_team=new_team
        )
        db.commit()
        db.refresh(entry)
    except DomainError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    member = db.get(LeagueMember, entry.member_id)
    team = db.get(Team, entry.team_id)
    return {
        "id": str(entry.public_id),
        "member_id": str(member.public_id) if member else None,
        "team_id": str(team.public_id) if team else None,
        "source": entry.source,
    }


