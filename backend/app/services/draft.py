"""Linear/snake on-clock draft with transactional pick validation."""

from __future__ import annotations

from app.services.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
)

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    DraftIdempotencyKey,
    DraftPick,
    DraftState,
    League,
    LeagueMember,
    PoolTeam,
    RosterEntry,
    Team,
    TeamPool,
)
from app.services.members import required_manager_count


@dataclass(frozen=True)
class OnClockInfo:
    pick_number: int
    round_number: int
    member_id: int
    member_public_id: str


def ordered_members(members: list[LeagueMember]) -> list[LeagueMember]:
    assigned = [m for m in members if m.draft_slot is not None]
    if len(assigned) != len(members):
        raise ConflictError("Draft order is incomplete")
    ordered = sorted(assigned, key=lambda m: m.draft_slot or 0)
    slots = [m.draft_slot for m in ordered]
    if slots != list(range(1, len(ordered) + 1)):
        raise ConflictError("Draft slots must be contiguous 1..N")
    return ordered


def on_clock_member(
    *,
    draft_style: str,
    ordered: list[LeagueMember],
    pick_number: int,
) -> tuple[LeagueMember, int]:
    """Return (member, round_number) for the given 1-based pick number."""
    if not ordered:
        raise ConflictError("No managers in draft order")
    n = len(ordered)
    round_number = ((pick_number - 1) // n) + 1
    index = (pick_number - 1) % n
    if draft_style == "snake" and round_number % 2 == 0:
        index = n - 1 - index
    elif draft_style not in {"linear", "snake"}:
        raise DomainError(f"Unsupported draft_style: {draft_style}")
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


def find_idempotent_pick(
    db: Session,
    *,
    league_id: int,
    member_id: int,
    idempotency_key: str,
) -> DraftPick | None:
    """Return existing pick for key, or None if key unused.

    A row with pick_id NULL means the key was spent but the pick was removed —
    treat as conflict so the same key cannot drive a new pick.
    """
    row = db.scalars(
        select(DraftIdempotencyKey).where(
            DraftIdempotencyKey.league_id == league_id,
            DraftIdempotencyKey.member_id == member_id,
            DraftIdempotencyKey.idempotency_key == idempotency_key,
        )
    ).first()
    if row is None:
        return None
    if row.pick_id is None:
        raise ConflictError("Idempotency key already used; refresh and retry with a new key",
        )
    pick = db.get(DraftPick, row.pick_id)
    if pick is None:
        raise ConflictError("Idempotency key already used; refresh and retry with a new key",
        )
    return pick


def _member_has_open_draft_slots(
    db: Session, member_id: int, pools: list[TeamPool]
) -> bool:
    for pool in pools:
        if not member_pool_filled(db, member_id, pool.id, pool.slot_count):
            return True
    return False


def make_pick(
    db: Session,
    *,
    league: League,
    picker_member: LeagueMember,
    team_public_id,
    allow_commissioner_override: bool = False,
    idempotency_key: str | None = None,
) -> DraftPick:
    """Transactional pick: lock draft_state, validate turn/availability, insert pick+roster."""
    state = db.scalars(
        select(DraftState).where(DraftState.league_id == league.id).with_for_update()
    ).first()
    if state is None or state.status != "open":
        raise ConflictError("Draft is not open")

    if idempotency_key:
        existing_pick = find_idempotent_pick(
            db,
            league_id=league.id,
            member_id=picker_member.id,
            idempotency_key=idempotency_key,
        )
        if existing_pick is not None:
            return existing_pick

    members = list(
        db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    )
    ordered = ordered_members(members)
    pools = list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all())

    # Auto-advance past members whose roster is already full (e.g. heavy preassigns).
    safety = max(1, len(ordered) * max(1, sum(p.slot_count for p in pools)) + 1)
    for _ in range(safety):
        expected, round_number = on_clock_member(
            draft_style=league.draft_style,
            ordered=ordered,
            pick_number=state.current_pick_number,
        )
        if _member_has_open_draft_slots(db, expected.id, pools):
            break
        state.current_pick_number += 1
        if _draft_is_complete(db, league, ordered):
            state.status = "complete"
            league.status = "active"
            db.flush()
            raise ConflictError("Draft completed — no open roster slots remain")
    else:
        raise ConflictError("Unable to find an on-clock manager with open slots")

    if expected.id != picker_member.id and not (
        allow_commissioner_override and picker_member.is_commissioner
    ):
        raise ForbiddenError("It is not your turn")

    acting_member = expected if allow_commissioner_override else picker_member

    team = db.scalars(select(Team).where(Team.public_id == team_public_id)).first()
    if team is None:
        raise NotFoundError("Team not found")

    existing = db.scalars(
        select(RosterEntry).where(
            RosterEntry.league_id == league.id,
            RosterEntry.team_id == team.id,
        )
    ).first()
    if existing:
        raise ConflictError("Team already drafted")

    pool_team = db.scalars(
        select(PoolTeam)
        .join(TeamPool, TeamPool.id == PoolTeam.pool_id)
        .where(TeamPool.league_id == league.id, PoolTeam.team_id == team.id)
    ).first()
    if pool_team is None:
        raise DomainError("Team is not in any pool for this league")

    pool = db.get(TeamPool, pool_team.pool_id)
    assert pool is not None
    if member_pool_filled(db, acting_member.id, pool.id, pool.slot_count):
        raise ConflictError("Roster slot for this pool is full")

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

    # SAVEPOINT: IntegrityError rolls back only this block (autoflush=False needs flush
    # before _draft_is_complete so the new roster row is visible).
    try:
        with db.begin_nested():
            db.add(pick)
            db.add(roster)
            state.current_pick_number += 1
            db.flush()
            if _draft_is_complete(db, league, ordered):
                state.status = "complete"
                league.status = "active"
            if idempotency_key:
                db.add(
                    DraftIdempotencyKey(
                        league_id=league.id,
                        member_id=picker_member.id,
                        idempotency_key=idempotency_key,
                        pick_id=pick.id,
                    )
                )
                db.flush()
    except IntegrityError as exc:
        if idempotency_key:
            existing = find_idempotent_pick(
                db,
                league_id=league.id,
                member_id=picker_member.id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                return existing
        raise ConflictError("Pick conflict (already taken or not your turn)") from exc

    return pick


def _draft_is_complete(db: Session, league: League, ordered: list[LeagueMember]) -> bool:
    pools = list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all())
    for member in ordered:
        for pool in pools:
            if not member_pool_filled(db, member.id, pool.id, pool.slot_count):
                return False
    return True


def reset_draft(db: Session, league: League) -> DraftState:
    """Wipe draft picks and draft-sourced rosters; return league to pre_draft.

    Keeps draft order (member slots) and preassigned roster entries.
    """
    for key in db.scalars(
        select(DraftIdempotencyKey).where(DraftIdempotencyKey.league_id == league.id)
    ).all():
        db.delete(key)
    for pick in db.scalars(select(DraftPick).where(DraftPick.league_id == league.id)).all():
        db.delete(pick)
    for entry in db.scalars(
        select(RosterEntry).where(
            RosterEntry.league_id == league.id,
            RosterEntry.source.in_(("draft", "commissioner")),
        )
    ).all():
        db.delete(entry)

    state = db.scalars(select(DraftState).where(DraftState.league_id == league.id)).first()
    if state is None:
        state = DraftState(league_id=league.id, current_pick_number=1, status="pending")
        db.add(state)
    else:
        state.current_pick_number = 1
        state.status = "pending"
    league.status = "pre_draft"
    db.flush()
    return state


def undo_last_pick(db: Session, league: League) -> DraftPick:
    """Commissioner undo of the most recent draft pick (open or just-completed)."""
    state = db.scalars(
        select(DraftState).where(DraftState.league_id == league.id).with_for_update()
    ).first()
    if state is None or state.status not in {"open", "complete"}:
        raise ConflictError("Undo only allowed while draft is open or just completed")
    if state.current_pick_number <= 1:
        raise ConflictError("No picks to undo")
    pick_number = state.current_pick_number - 1
    pick = db.scalars(
        select(DraftPick).where(
            DraftPick.league_id == league.id,
            DraftPick.pick_number == pick_number,
        )
    ).first()
    if pick is None:
        raise ConflictError("Last pick not found")
    roster = db.scalars(
        select(RosterEntry).where(
            RosterEntry.league_id == league.id,
            RosterEntry.team_id == pick.team_id,
            RosterEntry.source == "draft",
        )
    ).first()
    for key in db.scalars(
        select(DraftIdempotencyKey).where(DraftIdempotencyKey.pick_id == pick.id)
    ).all():
        db.delete(key)
    if roster is not None:
        db.delete(roster)
    db.delete(pick)
    state.current_pick_number = pick_number
    state.status = "open"
    league.status = "drafting"
    db.flush()
    return pick


def reassign_roster_entry(
    db: Session,
    league: League,
    *,
    entry: RosterEntry,
    new_member: LeagueMember | None = None,
    new_team: Team | None = None,
) -> RosterEntry:
    """Reassign ownership and/or replace team after draft is complete."""
    state = db.scalars(select(DraftState).where(DraftState.league_id == league.id)).first()
    if state is not None and state.status == "open":
        raise ConflictError("During an open draft use undo-last-pick instead of roster edit")
    if new_member is not None:
        if new_member.league_id != league.id:
            raise ConflictError("Manager is not in this league")
        pool = db.get(TeamPool, entry.pool_id)
        if pool is not None:
            count = db.scalars(
                select(RosterEntry).where(
                    RosterEntry.league_id == league.id,
                    RosterEntry.member_id == new_member.id,
                    RosterEntry.pool_id == entry.pool_id,
                    RosterEntry.id != entry.id,
                )
            ).all()
            if len(list(count)) >= pool.slot_count:
                raise ConflictError("Destination manager has no open roster slots in this pool")
        entry.member_id = new_member.id
    if new_team is not None:
        other = db.scalars(
            select(RosterEntry).where(
                RosterEntry.league_id == league.id,
                RosterEntry.team_id == new_team.id,
                RosterEntry.id != entry.id,
            )
        ).first()
        if other is not None:
            raise ConflictError("Team already on another roster")
        in_pool = db.scalars(
            select(PoolTeam).where(
                PoolTeam.pool_id == entry.pool_id,
                PoolTeam.team_id == new_team.id,
            )
        ).first()
        if in_pool is None:
            raise ConflictError("Replacement team is not in this pool")
        entry.team_id = new_team.id
        entry.source = "commissioner"
    db.flush()
    return entry


def open_draft(db: Session, league: League) -> DraftState:
    if league.status not in {"pre_draft", "drafting"}:
        raise ConflictError(f"Cannot open draft from league status {league.status}")
    members = list(db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all())
    required = required_manager_count(league)
    if required is None:
        raise ConflictError(
            "Set the required number of managers in league settings before opening the draft"
        )
    if len(members) != required:
        raise ConflictError(
            f"Need exactly {required} managers to open the draft (have {len(members)})"
        )
    ordered = ordered_members(members)
    pools = list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all())
    if any(p.slot_count < 1 for p in pools):
        raise ConflictError("All draftable pools need slot_count >= 1")

    mode = (league.preassign_mode or "none").lower()
    if mode in {"supported", "optional"}:
        preassigns = list(
            db.scalars(
                select(RosterEntry).where(
                    RosterEntry.league_id == league.id,
                    RosterEntry.source == "preassigned",
                )
            ).all()
        )
        team_ids = [e.team_id for e in preassigns]
        if len(team_ids) != len(set(team_ids)):
            raise ConflictError(
                {
                    "message": "preassign validation failed",
                    "blockers": ["duplicate preassigned team"],
                }
            )
        if mode == "supported":
            by_member = {m.id: 0 for m in ordered}
            for entry in preassigns:
                if entry.member_id in by_member:
                    by_member[entry.member_id] += 1
            missing = [mid for mid, count in by_member.items() if count < 1]
            extras = [mid for mid, count in by_member.items() if count > 1]
            blockers: list[str] = []
            if missing:
                blockers.append(f"managers missing supported preassign: {missing}")
            if extras:
                blockers.append(f"managers with multiple preassigns: {extras}")
            if blockers:
                raise ConflictError({"message": "preassign validation failed", "blockers": blockers})

    state = db.scalars(select(DraftState).where(DraftState.league_id == league.id)).first()
    if state is None:
        state = DraftState(league_id=league.id, current_pick_number=1, status="open")
        db.add(state)
    else:
        if state.status == "complete":
            raise ConflictError("Draft already complete")
        state.status = "open"
    league.status = "drafting"
    db.flush()
    return state