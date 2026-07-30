"""Curated football-data.org free-plan competitions + editable domestic tiers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompetitionTier

TeamKind = Literal["national_men", "national_women", "club"]


class AvailableCompetition(TypedDict):
    code: str
    label: str
    key: str
    team_kind: TeamKind
    domestic_tier: int | None


# Codes available on the football-data.org free plan.
# domestic_tier: curated default (API has no tier field). DB overrides via competition_tiers.
AVAILABLE_COMPETITIONS: tuple[AvailableCompetition, ...] = (
    {
        "code": "WC",
        "label": "FIFA World Cup",
        "key": "fifa_world_cup",
        "team_kind": "national_men",
        "domestic_tier": None,
    },
    {
        "code": "CL",
        "label": "UEFA Champions League",
        "key": "uefa_champions_league",
        "team_kind": "club",
        "domestic_tier": None,
    },
    {
        "code": "BL1",
        "label": "Bundesliga",
        "key": "bundesliga",
        "team_kind": "club",
        "domestic_tier": 1,
    },
    {
        "code": "DED",
        "label": "Eredivisie",
        "key": "eredivisie",
        "team_kind": "club",
        "domestic_tier": 1,
    },
    {
        "code": "BSA",
        "label": "Campeonato Brasileiro Série A",
        "key": "campeonato_brasileiro_serie_a",
        "team_kind": "club",
        "domestic_tier": 1,
    },
    {
        "code": "PD",
        "label": "Primera Division",
        "key": "primera_division",
        "team_kind": "club",
        "domestic_tier": 1,
    },
    {
        "code": "FL1",
        "label": "Ligue 1",
        "key": "ligue_1",
        "team_kind": "club",
        "domestic_tier": 1,
    },
    {
        "code": "ELC",
        "label": "Championship",
        "key": "championship",
        "team_kind": "club",
        "domestic_tier": 2,
    },
    {
        "code": "PPL",
        "label": "Primeira Liga",
        "key": "primeira_liga",
        "team_kind": "club",
        "domestic_tier": 1,
    },
    {
        "code": "EC",
        "label": "European Championship",
        "key": "european_championship",
        "team_kind": "national_men",
        "domestic_tier": None,
    },
    {
        "code": "SA",
        "label": "Serie A",
        "key": "serie_a",
        "team_kind": "club",
        "domestic_tier": 1,
    },
    {
        "code": "PL",
        "label": "Premier League",
        "key": "premier_league",
        "team_kind": "club",
        "domestic_tier": 1,
    },
)

AVAILABLE_COMPETITION_CODES: frozenset[str] = frozenset(
    c["code"] for c in AVAILABLE_COMPETITIONS
)

_TEAM_KIND_BY_CODE: dict[str, TeamKind] = {
    c["code"]: c["team_kind"] for c in AVAILABLE_COMPETITIONS
}

_CURATED_DOMESTIC_TIER_BY_CODE: dict[str, int | None] = {
    c["code"]: c["domestic_tier"] for c in AVAILABLE_COMPETITIONS
}

_NATIONAL_KINDS: frozenset[str] = frozenset({"national_men", "national_women"})


def normalize_competition_code(code: str | None) -> str | None:
    if code is None:
        return None
    trimmed = code.strip().upper()
    return trimmed or None


def default_competition_type_for_code(code: str | None) -> str | None:
    """Best-effort competition type from curated catalog (no provider call).

    Domestic leagues (tier set) → ``LEAGUE``; other curated codes → ``CUP``.
    Unknown codes return ``None``.
    """
    normalized = normalize_competition_code(code)
    if normalized is None or normalized not in _CURATED_DOMESTIC_TIER_BY_CODE:
        return None
    return "LEAGUE" if _CURATED_DOMESTIC_TIER_BY_CODE[normalized] is not None else "CUP"


def is_allowed_competition_code(code: str | None) -> bool:
    normalized = normalize_competition_code(code)
    if normalized is None:
        return False
    return normalized in AVAILABLE_COMPETITION_CODES


def team_kind_for_competition(code: str | None) -> TeamKind | None:
    normalized = normalize_competition_code(code)
    if normalized is None:
        return None
    return _TEAM_KIND_BY_CODE.get(normalized)


def curated_domestic_tier(code: str | None) -> int | None:
    """Default domestic ladder tier from the curated catalog (no DB)."""
    normalized = normalize_competition_code(code)
    if normalized is None:
        return None
    return _CURATED_DOMESTIC_TIER_BY_CODE.get(normalized)


def domestic_tier_for_competition(code: str | None) -> int | None:
    """Curated default tier. Prefer ``resolve_domestic_tiers`` when a DB session is available."""
    return curated_domestic_tier(code)


def ensure_competition_tiers(db: Session) -> list[CompetitionTier]:
    """Insert missing curated competition rows; leave existing admin edits untouched."""
    existing = {
        row.competition_code: row
        for row in db.scalars(select(CompetitionTier)).all()
    }
    changed = False
    for entry in AVAILABLE_COMPETITIONS:
        code = entry["code"]
        if code in existing:
            continue
        row = CompetitionTier(
            competition_code=code,
            domestic_tier=entry["domestic_tier"],
            updated_at=datetime.now(UTC),
        )
        db.add(row)
        existing[code] = row
        changed = True
    if changed:
        db.flush()
    return [existing[c["code"]] for c in AVAILABLE_COMPETITIONS if c["code"] in existing]


def resolve_domestic_tiers(db: Session) -> dict[str, int | None]:
    """Map competition_code → domestic_tier from DB (seeded with curated defaults)."""
    ensure_competition_tiers(db)
    rows = db.scalars(select(CompetitionTier)).all()
    by_code = {row.competition_code.upper(): row.domestic_tier for row in rows}
    # Fill any curated codes still missing (should not happen after ensure).
    for entry in AVAILABLE_COMPETITIONS:
        by_code.setdefault(entry["code"], entry["domestic_tier"])
    return by_code


def list_competition_tiers_for_admin(db: Session) -> list[dict]:
    """Admin listing joined with curated labels/kinds."""
    tiers = resolve_domestic_tiers(db)
    rows: list[dict] = []
    for entry in AVAILABLE_COMPETITIONS:
        rows.append(
            {
                "code": entry["code"],
                "label": entry["label"],
                "key": entry["key"],
                "team_kind": entry["team_kind"],
                "domestic_tier": tiers.get(entry["code"], entry["domestic_tier"]),
                "default_domestic_tier": entry["domestic_tier"],
            }
        )
    # Sort: numbered tiers first (asc), then cups (None), then by label.
    def sort_key(row: dict) -> tuple:
        tier = row["domestic_tier"]
        return (1 if tier is None else 0, tier or 0, row["label"].lower())

    rows.sort(key=sort_key)
    return rows


def update_competition_tiers(
    db: Session,
    updates: list[tuple[str, int | None]],
) -> list[dict]:
    """Apply admin tier edits for known competition codes."""
    ensure_competition_tiers(db)
    by_code = {
        row.competition_code.upper(): row
        for row in db.scalars(select(CompetitionTier)).all()
    }
    now = datetime.now(UTC)
    for raw_code, tier in updates:
        code = normalize_competition_code(raw_code)
        if code is None or code not in AVAILABLE_COMPETITION_CODES:
            continue
        if tier is not None and int(tier) < 1:
            raise ValueError(f"domestic_tier must be >= 1 or null for {code}")
        row = by_code.get(code)
        if row is None:
            row = CompetitionTier(
                competition_code=code,
                domestic_tier=tier,
                updated_at=now,
            )
            db.add(row)
            by_code[code] = row
        else:
            row.domestic_tier = tier
            row.updated_at = now
    db.flush()
    return list_competition_tiers_for_admin(db)


def national_competition_codes(kind: TeamKind | None = None) -> frozenset[str]:
    if kind is None:
        return frozenset(
            c["code"] for c in AVAILABLE_COMPETITIONS if c["team_kind"] in _NATIONAL_KINDS
        )
    return frozenset(c["code"] for c in AVAILABLE_COMPETITIONS if c["team_kind"] == kind)


def should_apply_team_kind(current: str | None, incoming: TeamKind) -> bool:
    """National kinds win over club; never downgrade national → club."""
    if current == incoming:
        return False
    if current in _NATIONAL_KINDS and incoming == "club":
        return False
    return True
