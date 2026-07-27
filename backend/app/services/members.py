"""Helpers for labeling and managing league managers."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
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


def renumber_draft_slots(members: list[LeagueMember]) -> None:
    """Assign contiguous draft slots 1..N, preserving relative order.

    Members without a slot are sorted after those with slots. Clears slots
    first so unique (league_id, draft_slot) indexes do not conflict mid-update.
    """
    ordered = sorted(
        members,
        key=lambda m: (
            m.draft_slot is None,
            m.draft_slot if m.draft_slot is not None else 0,
            m.id,
        ),
    )
    for member in ordered:
        member.draft_slot = None
    for index, member in enumerate(ordered, start=1):
        member.draft_slot = index


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
    """Return the next append-only draft slot (max existing + 1, or 1).

    Considers both current members and pending invites that already reserved a
    slot, so join-link auto-assignment cannot steal a reserved invite slot.

    Locks the league row so concurrent join / invite-accept callers serialize
    slot assignment and avoid colliding on the partial unique index.
    """
    db.get(League, league_id, with_for_update=True)
    member_max = db.scalar(
        select(func.max(LeagueMember.draft_slot)).where(LeagueMember.league_id == league_id)
    )
    invite_max = db.scalar(
        select(func.max(Invite.draft_slot)).where(
            Invite.league_id == league_id,
            Invite.status == "pending",
            Invite.draft_slot.is_not(None),
        )
    )
    return max(int(member_max or 0), int(invite_max or 0)) + 1


def join_or_return_member(
    db: Session,
    league: League,
    profile: Profile,
    *,
    is_commissioner: bool = False,
    draft_slot: int | None = None,
) -> tuple[LeagueMember, bool]:
    """Return existing membership or create one. Does not commit.

    New members without an explicit draft_slot get the next available slot.
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

    if draft_slot is None:
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
