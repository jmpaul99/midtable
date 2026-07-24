"""Helpers for labeling and managing league managers."""

from __future__ import annotations

from app.auth.jwt import MAX_DISPLAY_NAME_LEN
from app.models import LeagueMember, Profile


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
