"""Roster owner lookup helpers for league read models."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import League, LeagueMember, Profile, RosterEntry
from app.services.members import member_label


def owner_dict(
    member: LeagueMember,
    profile: Profile | None,
    source: str | None,
) -> dict[str, Any]:
    """Canonical owner payload for API read models."""
    return {
        "member_id": str(member.public_id),
        "display_name": member_label(member, profile),
        "team_name": (member.team_name.strip() if member.team_name else None),
        "acquired_via": source,
    }


def owner_by_team_id_for_league(db: Session, league: League) -> dict[int, dict[str, Any]]:
    """Map internal team id → owner dict for clubs on the league roster."""
    roster_entries = list(
        db.scalars(select(RosterEntry).where(RosterEntry.league_id == league.id)).all()
    )
    member_ids = {e.member_id for e in roster_entries}
    members_by_id = {
        m.id: m
        for m in (
            db.scalars(select(LeagueMember).where(LeagueMember.id.in_(member_ids))).all()
            if member_ids
            else []
        )
    }
    profile_ids = {m.profile_id for m in members_by_id.values() if m.profile_id}
    profiles_by_id = {
        p.id: p
        for p in (
            db.scalars(select(Profile).where(Profile.id.in_(profile_ids))).all()
            if profile_ids
            else []
        )
    }
    owner_by_team_id: dict[int, dict[str, Any]] = {}
    for roster_entry in roster_entries:
        member = members_by_id.get(roster_entry.member_id)
        if not member:
            continue
        profile = profiles_by_id.get(member.profile_id) if member.profile_id else None
        owner_by_team_id[roster_entry.team_id] = owner_dict(
            member, profile, roster_entry.source
        )
    return owner_by_team_id


def roster_entries_for_member(
    db: Session, *, league_id: int, member_id: int
) -> list[RosterEntry]:
    return list(
        db.scalars(
            select(RosterEntry).where(
                RosterEntry.league_id == league_id,
                RosterEntry.member_id == member_id,
            )
        ).all()
    )


def team_ids_for_member(db: Session, *, league_id: int, member_id: int) -> set[int]:
    return {e.team_id for e in roster_entries_for_member(db, league_id=league_id, member_id=member_id)}


def member_id_by_team_id_for_league(db: Session, league: League) -> dict[int, int]:
    """Map internal team id → owning member id for the league roster."""
    return {
        r.team_id: r.member_id
        for r in db.scalars(select(RosterEntry).where(RosterEntry.league_id == league.id)).all()
    }

