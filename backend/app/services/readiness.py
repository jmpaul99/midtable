"""League draft / sync readiness checklist evaluation."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import League, LeagueMember, PoolTeam, RosterEntry, TeamPool
from app.schemas.leagues import ReadinessCheck, ReadinessResponse
from app.services.preassign import effective_preassign_count, normalize_preassign_mode

ReadinessPurpose = Literal["draft", "sync"]


def evaluate_readiness(
    db: Session,
    league: League,
    *,
    purpose: ReadinessPurpose = "draft",
) -> ReadinessResponse:
    """Return a checklist filtered by purpose (draft open vs fixture sync)."""
    checks: list[ReadinessCheck] = []
    pools = list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all())
    scoring_pools = [p for p in pools if p.scores_match_results]

    if purpose == "draft":
        checks.extend(_draft_member_checks(db, league))
        checks.extend(_draft_preassign_checks(db, league, pools))
        checks.extend(_pools_check(pools, for_draft=True))
        checks.extend(_scoring_pools_check(pools, scoring_pools, purpose="draft"))
        for pool in pools:
            checks.extend(_draft_pool_checks(db, pool))
    else:
        checks.extend(_pools_check(pools, for_draft=False))
        checks.extend(_scoring_pools_check(pools, scoring_pools, purpose="sync"))
        for pool in scoring_pools:
            checks.extend(_sync_scoring_pool_checks(db, pool))

    errors = [c.detail or c.label for c in checks if c.status == "error"]
    warnings = [c.detail or c.label for c in checks if c.status == "warning"]
    return ReadinessResponse(
        ready=len(errors) == 0,
        checks=checks,
        errors=errors,
        warnings=warnings,
    )


def _draft_member_checks(db: Session, league: League) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    members = list(
        db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    )
    member_count = len(members)
    required = None
    config = league.config or {}
    if config.get("max_members") is not None:
        try:
            required = max(2, int(config["max_members"]))
        except (TypeError, ValueError):
            required = None

    if required is None:
        checks.append(
            ReadinessCheck(
                key="members",
                label="Manager roster size configured",
                status="error",
                detail="Set the required number of managers in league settings",
            )
        )
    elif member_count == required:
        checks.append(
            ReadinessCheck(
                key="members",
                label=f"Full manager roster ({required})",
                status="ok",
                detail=f"{member_count} of {required} managers joined",
            )
        )
    elif member_count < required:
        checks.append(
            ReadinessCheck(
                key="members",
                label=f"Full manager roster ({required})",
                status="error",
                detail=(
                    f"{member_count} of {required} managers joined — "
                    "invite the rest before drafting"
                ),
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key="members",
                label=f"Full manager roster ({required})",
                status="error",
                detail=(
                    f"{member_count} of {required} managers joined — "
                    "remove extras before drafting"
                ),
            )
        )

    missing_draft = sum(1 for m in members if m.draft_slot is None)
    if member_count == 0:
        checks.append(
            ReadinessCheck(
                key="draft_order",
                label="Draft order complete",
                status="error",
                detail="No managers to assign draft slots",
            )
        )
    elif missing_draft == 0:
        checks.append(
            ReadinessCheck(
                key="draft_order",
                label="Draft order complete",
                status="ok",
                detail=f"All {member_count} managers have a draft slot",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key="draft_order",
                label="Draft order complete",
                status="error",
                detail=f"{missing_draft} of {member_count} managers missing a draft slot",
            )
        )
    return checks


def _draft_preassign_checks(
    db: Session, league: League, pools: list[TeamPool]
) -> list[ReadinessCheck]:
    mode = normalize_preassign_mode(getattr(league, "preassign_mode", None))
    if mode not in {"optional", "required"}:
        return []

    n = effective_preassign_count(getattr(league, "preassign_count", None))
    members = list(
        db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    )
    preassigns = list(
        db.scalars(
            select(RosterEntry).where(
                RosterEntry.league_id == league.id,
                RosterEntry.source == "preassigned",
            )
        ).all()
    )
    checks: list[ReadinessCheck] = []
    team_ids = [e.team_id for e in preassigns]
    if len(team_ids) != len(set(team_ids)):
        checks.append(
            ReadinessCheck(
                key="preassigns:duplicates",
                label="Preassigned clubs unique",
                status="error",
                detail="The same club is preassigned more than once",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key="preassigns:duplicates",
                label="Preassigned clubs unique",
                status="ok",
                detail="No duplicate preassigned clubs",
            )
        )

    by_member = {m.id: 0 for m in members}
    for entry in preassigns:
        if entry.member_id in by_member:
            by_member[entry.member_id] += 1

    member_count = len(members)
    if mode == "required":
        wrong = sum(1 for count in by_member.values() if count != n)
        if wrong == 0 and member_count > 0:
            checks.append(
                ReadinessCheck(
                    key="preassigns",
                    label=f"Required preassigns ({n} per manager)",
                    status="ok",
                    detail=f"All {member_count} managers have exactly {n} preassigned club(s)",
                )
            )
        else:
            short = sum(1 for count in by_member.values() if count < n)
            over = sum(1 for count in by_member.values() if count > n)
            parts: list[str] = []
            if short:
                parts.append(f"{short} need more")
            if over:
                parts.append(f"{over} have too many")
            detail = (
                f"{wrong} of {member_count} managers need exactly {n} preassigned club(s)"
                + (f" — {'; '.join(parts)}" if parts else "")
            )
            checks.append(
                ReadinessCheck(
                    key="preassigns",
                    label=f"Required preassigns ({n} per manager)",
                    status="error",
                    detail=detail,
                )
            )
    else:
        over = sum(1 for count in by_member.values() if count > n)
        if over == 0:
            checks.append(
                ReadinessCheck(
                    key="preassigns",
                    label=f"Optional preassigns (max {n})",
                    status="ok",
                    detail=f"No manager exceeds {n} preassigned club(s)",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    key="preassigns",
                    label=f"Optional preassigns (max {n})",
                    status="error",
                    detail=f"{over} of {member_count} managers exceed {n} preassigned club(s)",
                )
            )

    # Guard against preassigns overflowing a competition's roster slot_count.
    pool_by_id = {p.id: p for p in pools}
    counts_by_member_pool: dict[tuple[int, int], int] = {}
    for entry in preassigns:
        pool_id = getattr(entry, "pool_id", None)
        if pool_id is None:
            continue
        key = (entry.member_id, pool_id)
        counts_by_member_pool[key] = counts_by_member_pool.get(key, 0) + 1
    over_slot = 0
    for (member_id, pool_id), count in counts_by_member_pool.items():
        pool = pool_by_id.get(pool_id)
        if pool is not None and count > int(pool.slot_count):
            over_slot += 1
    if over_slot == 0:
        checks.append(
            ReadinessCheck(
                key="preassigns:pool_slots",
                label="Preassigns within competition slots",
                status="ok",
                detail="No manager exceeds a competition's slot count via preassign",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key="preassigns:pool_slots",
                label="Preassigns within competition slots",
                status="error",
                detail=(
                    f"{over_slot} manager/competition pair(s) exceed competition slot_count"
                ),
            )
        )
    return checks


def _pools_check(pools: list[TeamPool], *, for_draft: bool) -> list[ReadinessCheck]:
    if pools:
        return [
            ReadinessCheck(
                key="pools",
                label="Competitions configured",
                status="ok",
                detail=f"{len(pools)} competition(s)",
            )
        ]
    detail = (
        "Add competitions in League settings → Competitions before the draft opens"
        if for_draft
        else "Add competitions in League settings → Competitions before syncing"
    )
    return [
        ReadinessCheck(
            key="pools",
            label="Competitions configured",
            status="error",
            detail=detail,
        )
    ]


def _scoring_pools_check(
    pools: list[TeamPool],
    scoring_pools: list[TeamPool],
    *,
    purpose: ReadinessPurpose,
) -> list[ReadinessCheck]:
    if not pools:
        return []
    if scoring_pools:
        return [
            ReadinessCheck(
                key="scoring_pools",
                label="Scoring competitions present",
                status="ok",
                detail=f"{len(scoring_pools)} competition(s) score match results",
            )
        ]
    status = "warning" if purpose == "draft" else "error"
    return [
        ReadinessCheck(
            key="scoring_pools",
            label="Scoring competitions present",
            status=status,
            detail="No competition has match scoring enabled — Sync will find nothing to pull",
        )
    ]


def _draft_pool_checks(db: Session, pool: TeamPool) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    label = pool.label or pool.key

    if pool.slot_count >= 1:
        checks.append(
            ReadinessCheck(
                key=f"slots:{pool.key}",
                label=f"{label}: roster slots",
                status="ok",
                detail=f"{pool.slot_count} slot(s) per manager",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key=f"slots:{pool.key}",
                label=f"{label}: roster slots",
                status="error",
                detail="slot_count must be at least 1",
            )
        )

    team_count = len(
        list(db.scalars(select(PoolTeam).where(PoolTeam.pool_id == pool.id)).all())
    )
    if team_count > 0:
        checks.append(
            ReadinessCheck(
                key=f"teams:{pool.key}",
                label=f"{label}: clubs loaded",
                status="ok",
                detail=f"{team_count} club(s)",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key=f"teams:{pool.key}",
                label=f"{label}: clubs loaded",
                status="warning" if not pool.scores_match_results else "error",
                detail="No clubs yet — use Bootstrap teams (or create-league load)",
            )
        )

    if pool.scores_match_results:
        checks.append(_provider_check(pool, severity="warning"))
    return checks


def _sync_scoring_pool_checks(db: Session, pool: TeamPool) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    label = pool.label or pool.key
    team_count = len(
        list(db.scalars(select(PoolTeam).where(PoolTeam.pool_id == pool.id)).all())
    )
    if team_count > 0:
        checks.append(
            ReadinessCheck(
                key=f"teams:{pool.key}",
                label=f"{label}: clubs loaded",
                status="ok",
                detail=f"{team_count} club(s)",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key=f"teams:{pool.key}",
                label=f"{label}: clubs loaded",
                status="warning",
                detail=(
                    "No clubs linked in this league yet — fixture sync still uses the "
                    "global team catalog; bootstrap before drafting"
                ),
            )
        )
    checks.append(_provider_check(pool, severity="error"))
    return checks


def _provider_check(
    pool: TeamPool, *, severity: Literal["error", "warning"]
) -> ReadinessCheck:
    label = pool.label or pool.key
    if pool.competition_code and pool.season_year:
        return ReadinessCheck(
            key=f"provider:{pool.key}",
            label=f"{label}: provider competition",
            status="ok",
            detail=f"{pool.competition_code} · {pool.season_year}",
        )
    missing = []
    if not pool.competition_code:
        missing.append("competition code")
    if not pool.season_year:
        missing.append("season year")
    return ReadinessCheck(
        key=f"provider:{pool.key}",
        label=f"{label}: provider competition",
        status=severity,
        detail=f"Missing {', '.join(missing)} — Sync skips this competition",
    )
