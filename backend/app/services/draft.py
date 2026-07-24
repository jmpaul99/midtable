"""Linear/snake on-clock draft with transactional pick validation."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import DraftPick, DraftState, League, LeagueMember, PoolTeam, RosterEntry, Team, TeamPool


@dataclass(frozen=True)
class OnClockInfo:
    pick_number: int
    round_number: int
    member_id: int
    member_public_id: str


def ordered_members(members: list[LeagueMember]) -> list[LeagueMember]:
    assigned = [m for m in members if m.draft_slot is not None]
    if len(assigned) != len(members):
        raise HTTPException(status_code=409, detail="Draft order is incomplete")
    ordered = sorted(assigned, key=lambda m: m.draft_slot or 0)
    slots = [m.draft_slot for m in ordered]
    if slots != list(range(1, len(ordered) + 1)):
        raise HTTPException(status_code=409, detail="Draft slots must be contiguous 1..N")
    return ordered


def on_clock_member(
    *,
    draft_style: str,
    ordered: list[LeagueMember],
    pick_number: int,
) -> tuple[LeagueMember, int]:
    """Return (member, round_number) for the given 1-based pick number."""
    if not ordered:
        raise HTTPException(status_code=409, detail="No members in draft order")
    n = len(ordered)
    round_number = ((pick_number - 1) // n) + 1
    index = (pick_number - 1) % n
    if draft_style == "snake" and round_number % 2 == 0:
        index = n - 1 - index
    elif draft_style not in {"linear", "snake"}:
        raise HTTPException(status_code=400, detail=f"Unsupported draft_style: {draft_style}")
    return ordered[index], round_number


def roster_slot_counts(league: League) -> dict[str, int]:
    """Derive per-pool slot counts from league pools."""
    return {pool.key: pool.slot_count for pool in league.pools}


def member_pool_filled(db: Session, member_id: int, pool_id: int, slot_count: int) -> bool:
    count = db.scalars(
        select(RosterEntry).where(
            RosterEntry.member_id == member_id,
            RosterEntry.pool_id == pool_id,
        )
    ).all()
    return len(count) >= slot_count


def make_pick(
    db: Session,
    *,
    league: League,
    picker_member: LeagueMember,
    team_public_id,
    allow_commissioner_override: bool = False,
) -> DraftPick:
    """Transactional pick: lock draft_state, validate turn/availability, insert pick+roster."""
    state = db.scalars(
        select(DraftState).where(DraftState.league_id == league.id).with_for_update()
    ).first()
    if state is None or state.status != "open":
        raise HTTPException(status_code=409, detail="Draft is not open")

    members = list(
        db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    )
    ordered = ordered_members(members)
    expected, round_number = on_clock_member(
        draft_style=league.draft_style,
        ordered=ordered,
        pick_number=state.current_pick_number,
    )

    if expected.id != picker_member.id and not (
        allow_commissioner_override and picker_member.is_commissioner
    ):
        raise HTTPException(status_code=403, detail="It is not your turn")

    acting_member = expected if allow_commissioner_override else picker_member

    team = db.scalars(select(Team).where(Team.public_id == team_public_id)).first()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    existing = db.scalars(
        select(RosterEntry).where(
            RosterEntry.league_id == league.id,
            RosterEntry.team_id == team.id,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Team already drafted")

    pool_team = db.scalars(
        select(PoolTeam)
        .join(TeamPool, TeamPool.id == PoolTeam.pool_id)
        .where(TeamPool.league_id == league.id, PoolTeam.team_id == team.id)
    ).first()
    if pool_team is None:
        raise HTTPException(status_code=400, detail="Team is not in any pool for this league")

    pool = db.get(TeamPool, pool_team.pool_id)
    assert pool is not None
    if member_pool_filled(db, acting_member.id, pool.id, pool.slot_count):
        raise HTTPException(status_code=409, detail="Roster slot for this pool is full")

    pick = DraftPick(
        league_id=league.id,
        pick_number=state.current_pick_number,
        round_number=round_number,
        member_id=acting_member.id,
        team_id=team.id,
        pool_id=pool.id,
    )
    roster = RosterEntry(
        league_id=league.id,
        member_id=acting_member.id,
        team_id=team.id,
        pool_id=pool.id,
        source="draft",
    )
    db.add(pick)
    db.add(roster)

    # Advance pick; complete when no draftable slots remain for anyone
    state.current_pick_number += 1
    if _draft_is_complete(db, league, ordered):
        state.status = "complete"
        league.status = "active"

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Pick conflict (already taken or not your turn)"
        ) from exc
    return pick


def _draft_is_complete(db: Session, league: League, ordered: list[LeagueMember]) -> bool:
    pools = list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all())
    for member in ordered:
        for pool in pools:
            if not member_pool_filled(db, member.id, pool.id, pool.slot_count):
                return False
    return True


def open_draft(db: Session, league: League) -> DraftState:
    ordered_members(list(db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()))
    state = db.scalars(select(DraftState).where(DraftState.league_id == league.id)).first()
    if state is None:
        state = DraftState(league_id=league.id, current_pick_number=1, status="open")
        db.add(state)
    else:
        if state.status == "complete":
            raise HTTPException(status_code=409, detail="Draft already complete")
        state.status = "open"
    league.status = "drafting"
    db.flush()
    return state
