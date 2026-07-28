"""Helpers for labeling and managing league managers."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import MAX_DISPLAY_NAME_LEN
from app.models import Invite, League, LeagueMember, Profile


def default_team_name(display_name: str | None) -> str:
    """Build a per-league default like \"Alex's Team\"."""
    base = (display_name or "Manager").strip() or "Manager"
    suffix = "'s Team"
    max_base = MAX_DISPLAY_NAME_LEN - len(suffix)
    if len(base) > max_base:
        base = base[:max_base].rstrip() or "Manager"
    return f"{base}{suffix}"


def member_label(member: LeagueMember, profile: Profile | None) -> str:
    """Fantasy team name, then profile display name, then a safe fallback."""
    if member.team_name and member.team_name.strip():
        return member.team_name.strip()
    if profile and profile.display_name and profile.display_name.strip():
        return profile.display_name.strip()
    return "Manager"


def count_commissioners(members: list[LeagueMember]) -> int:
    return sum(1 for m in members if m.is_commissioner)


def is_sole_commissioner(member: LeagueMember, members: list[LeagueMember]) -> bool:
    return bool(member.is_commissioner and count_commissioners(members) == 1)


def assign_draft_slots(db: Session, members_in_order: list[LeagueMember]) -> None:
    """Assign contiguous draft slots 1..N in the given order.

    Clears existing slots and flushes before reassignment so the unique
    (league_id, draft_slot) partial index does not conflict when swapping
    or shifting slots.
    """
    for member in members_in_order:
        member.draft_slot = None
    db.flush()
    for index, member in enumerate(members_in_order, start=1):
        member.draft_slot = index


def renumber_draft_slots(db: Session, members: list[LeagueMember]) -> None:
    """Assign contiguous draft slots 1..N, preserving relative order.

    Members without a slot are sorted after those with slots.
    """
    ordered = sorted(
        members,
        key=lambda m: (
            m.draft_slot is None,
            m.draft_slot if m.draft_slot is not None else 0,
            m.id,
        ),
    )
    assign_draft_slots(db, ordered)


def required_manager_count(league) -> int | None:
    """Configured roster size from league.config.max_members, if set."""
    config = getattr(league, "config", None) or {}
    if "max_members" not in config or config.get("max_members") is None:
        return None
    try:
        return max(2, int(config["max_members"]))
    except (TypeError, ValueError):
        return None


def next_draft_slot(db: Session, league_id: int) -> int:
    """Return the lowest free draft slot (1, 2, …) for this league.

    Considers both current members and pending invites that already reserved a
    slot, so join-link auto-assignment cannot steal a reserved invite slot or
    create gaps that break open_draft's contiguous 1..N requirement.

    Locks the league row so concurrent join / invite-accept callers serialize
    slot assignment and avoid colliding on the partial unique index.
    """
    db.get(League, league_id, with_for_update=True)
    used = {
        int(slot)
        for slot in db.scalars(
            select(LeagueMember.draft_slot).where(
                LeagueMember.league_id == league_id,
                LeagueMember.draft_slot.is_not(None),
            )
        ).all()
    }
    used.update(
        int(slot)
        for slot in db.scalars(
            select(Invite.draft_slot).where(
                Invite.league_id == league_id,
                Invite.status == "pending",
                Invite.draft_slot.is_not(None),
            )
        ).all()
    )
    slot = 1
    while slot in used:
        slot += 1
    return slot


def join_or_return_member(
    db: Session,
    league: League,
    profile: Profile,
    *,
    is_commissioner: bool = False,
    draft_slot: int | None = None,
) -> tuple[LeagueMember, bool]:
    """Return existing membership or create one. Does not commit.

    New members in pre_draft without an explicit draft_slot get the next
    available slot. Mid-draft joiners keep a null slot so they are not folded
    into the active turn order.
    Raises HTTPException 409 when the league is closed or full.
    Caller owns draft_slot uniqueness checks and invite/audit side effects.
    """
    existing = db.scalars(
        select(LeagueMember).where(
            LeagueMember.league_id == league.id,
            LeagueMember.profile_id == profile.id,
        )
    ).first()
    if existing:
        return existing, False

    if league.status not in {"pre_draft", "drafting"}:
        raise HTTPException(status_code=409, detail="League is not accepting new managers")

    member_count = len(
        list(db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all())
    )
    max_members = required_manager_count(league)
    if max_members is not None and member_count >= max_members:
        raise HTTPException(
            status_code=409,
            detail=f"League is full ({max_members} managers)",
        )

    if draft_slot is None and league.status == "pre_draft":
        # Auto-append only before the draft starts. Mid-draft assignment would
        # expand turn order while current_pick_number still reflects the
        # earlier manager count.
        draft_slot = next_draft_slot(db, league.id)

    member = LeagueMember(
        league_id=league.id,
        profile_id=profile.id,
        is_commissioner=is_commissioner,
        draft_slot=draft_slot,
        team_name=default_team_name(profile.display_name),
    )
    db.add(member)
    return member, True
