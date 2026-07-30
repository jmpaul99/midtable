"""Linear/snake on-clock draft with transactional pick validation."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    DraftIdempotencyKey,
    DraftPick,
    DraftState,
    League,
    LeagueMember,
    PoolTeam,
    RankingList,
    RosterEntry,
    StandingsSnapshotRow,
    Team,
    TeamPool,
)
from app.services.competitions import resolve_domestic_tiers
from app.services.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
)
from app.logging_config import log_id
from app.services.ranking_catalog import freeze_catalog_for_league_lock, ranks_for_league
from app.services.readiness import evaluate_readiness
from app.services.scoring import RankedTeam, UpsetRules
from app.services.standings import (
    previous_final_snapshot_for_competition,
    zeroed_opener_snapshot_for_competition,
)

logger = logging.getLogger(__name__)

AutopickMode = Literal["ranking", "table", "random"]

# Ranking/table order is stable for an open draft (freeze snapshot). Cache until
# open/reset — not a short TTL — so hour-long drafts do not rebuild.
_draft_order_cache: dict[int, dict[tuple[int, int], int]] = {}


def invalidate_draft_order_cache(league_id: int | None = None) -> None:
    if league_id is None:
        _draft_order_cache.clear()
    else:
        _draft_order_cache.pop(league_id, None)


@dataclass(frozen=True)
class OnClockInfo:
    pick_number: int
    round_number: int
    member_id: int
    member_public_id: str


@dataclass(frozen=True)
class AutopickSelection:
    mode: AutopickMode
    team: Team | None
    pool: TeamPool | None


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
    count = db.scalar(
        select(func.count())
        .select_from(RosterEntry)
        .where(
            RosterEntry.member_id == member_id,
            RosterEntry.pool_id == pool_id,
        )
    )
    return int(count or 0) >= slot_count


def _roster_fill_counts(
    db: Session, *, league_id: int
) -> dict[tuple[int, int], int]:
    """Map (member_id, pool_id) → roster entry count for one league."""
    rows = db.execute(
        select(RosterEntry.member_id, RosterEntry.pool_id, func.count())
        .where(RosterEntry.league_id == league_id)
        .group_by(RosterEntry.member_id, RosterEntry.pool_id)
    ).all()
    return {(int(member_id), int(pool_id)): int(n) for member_id, pool_id, n in rows}


def _cached_ranks_for_league(
    db: Session, league: League, upset: UpsetRules
) -> dict[int, RankedTeam] | None:
    """Ranks come from freeze/TeamRanking rows — cheap enough to read each call."""
    return ranks_for_league(db, league, upset)


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


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def apply_pick_deadline(
    state: DraftState,
    league: League,
    *,
    now: datetime | None = None,
) -> None:
    """Set or clear pick_deadline_at from league.pick_timer_seconds."""
    now = now or datetime.now(UTC)
    seconds = league.pick_timer_seconds
    if state.status == "open" and seconds is not None and int(seconds) > 0:
        state.pick_deadline_at = now + timedelta(seconds=int(seconds))
    else:
        state.pick_deadline_at = None


def peek_on_clock_member(
    db: Session,
    *,
    league: League,
    state: DraftState,
    ordered: list[LeagueMember],
    pools: list[TeamPool],
) -> tuple[LeagueMember, int] | None:
    """Return (on-clock manager, round) with open slots without mutating pick number."""
    fills = _roster_fill_counts(db, league_id=league.id)

    def has_open(member_id: int) -> bool:
        for pool in pools:
            if fills.get((member_id, pool.id), 0) < int(pool.slot_count):
                return True
        return False

    safety = max(1, len(ordered) * max(1, sum(p.slot_count for p in pools)) + 1)
    pick_number = state.current_pick_number
    for _ in range(safety):
        expected, round_number = on_clock_member(
            draft_style=league.draft_style,
            ordered=ordered,
            pick_number=pick_number,
        )
        if has_open(expected.id):
            return expected, round_number
        pick_number += 1
        if all(not has_open(m.id) for m in ordered):
            return None
    return None


def _available_candidates(
    db: Session,
    *,
    league: League,
    member: LeagueMember,
    pools: list[TeamPool],
) -> list[tuple[Team, TeamPool]]:
    drafted_ids = set(
        db.scalars(
            select(RosterEntry.team_id).where(RosterEntry.league_id == league.id)
        ).all()
    )
    fills = _roster_fill_counts(db, league_id=league.id)
    open_pools = [
        pool
        for pool in pools
        if fills.get((member.id, pool.id), 0) < int(pool.slot_count)
    ]
    if not open_pools:
        return []

    pool_by_id = {p.id: p for p in open_pools}
    rows = db.execute(
        select(Team, PoolTeam.pool_id)
        .join(PoolTeam, PoolTeam.team_id == Team.id)
        .where(PoolTeam.pool_id.in_(pool_by_id.keys()))
    ).all()
    candidates: list[tuple[Team, TeamPool]] = []
    for team, pool_id in rows:
        if team.id in drafted_ids:
            continue
        pool = pool_by_id.get(int(pool_id))
        if pool is not None:
            candidates.append((team, pool))
    return candidates


@dataclass(frozen=True)
class CompetitionTableState:
    """Previous-final rows + zeroed-opener squad for one competition season."""

    previous_rows: dict[int, StandingsSnapshotRow]
    # None when the zeroed opener is missing; set difference is then unavailable.
    opener_ids: frozenset[int] | None

    @property
    def departed_ids(self) -> frozenset[int]:
        """In previous-final but not in zeroed opener (left the competition)."""
        if self.opener_ids is None:
            return frozenset()
        return frozenset(self.previous_rows) - self.opener_ids

    @property
    def arrival_ids(self) -> frozenset[int]:
        """In zeroed opener but not in previous-final (new to the competition)."""
        if self.opener_ids is None:
            return frozenset()
        return self.opener_ids - frozenset(self.previous_rows)


def _table_row_lookup(
    db: Session, pools: list[TeamPool]
) -> dict[str, CompetitionTableState]:
    """Load previous-final + zeroed opener per competition for draft ordering.

    Promotion/relegation is inferred from set difference between those snapshots
    (not from finishing positions alone), since playoffs/etc. vary by league.
    """
    by_comp: dict[str, CompetitionTableState] = {}
    seen_keys: set[tuple[str, str, int]] = set()
    for pool in pools:
        if not pool.competition_code or not pool.season_year:
            continue
        key = (
            pool.provider or "football-data.org",
            pool.competition_code.upper(),
            int(pool.season_year),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        prev = previous_final_snapshot_for_competition(
            db,
            provider=key[0],
            competition_code=key[1],
            season_year=key[2],
        )
        previous_rows: dict[int, StandingsSnapshotRow] = {}
        if prev is not None:
            previous_rows = {row.team_id: row for row in prev.rows}

        opener = zeroed_opener_snapshot_for_competition(
            db,
            provider=key[0],
            competition_code=key[1],
            season_year=key[2],
        )
        opener_ids: frozenset[int] | None = None
        if opener is not None:
            opener_ids = frozenset(row.team_id for row in opener.rows)

        if not previous_rows and opener_ids is None:
            continue
        by_comp[key[1]] = CompetitionTableState(
            previous_rows=previous_rows,
            opener_ids=opener_ids,
        )
    return by_comp


def sort_candidates_for_autopick(
    db: Session,
    *,
    league: League,
    candidates: list[tuple[Team, TeamPool]],
) -> tuple[list[tuple[Team, TeamPool]], AutopickMode]:
    """Sort candidates best-first using the league's rank source.

    When no ranking/table data is available, sorts alphabetically (stable UI for
    random autopick mode).

    Table mode (per domestic tier, best first):
    1. Relegated into the pool (left a better-tier competition's opener)
    2. Stayers (in both previous-final and zeroed opener), by previous-final rank
    3. New to the competition (in opener only / not in previous-final)
    """
    if not candidates:
        return [], "random"

    upset = UpsetRules.from_config(league.upset_rules)
    if upset.rank_source == "fixed_ranking_at_event_start":
        ranks = _cached_ranks_for_league(db, league, upset)
        if ranks:
            def fixed_key(item: tuple[Team, TeamPool]) -> tuple:
                team, _ = item
                ranked = team.id in ranks
                rank = ranks[team.id].rank if ranked else 0
                return (0 if ranked else 1, rank, (team.name or "").lower())

            return sorted(candidates, key=fixed_key), "ranking"

    if upset.rank_source == "league_table_at_kickoff":
        pools = list({p.id: p for _, p in candidates}.values())
        by_comp = _table_row_lookup(db, pools)
        if any(s.previous_rows for s in by_comp.values()):
            tier_by_code = resolve_domestic_tiers(db)

            def table_key(item: tuple[Team, TeamPool]) -> tuple:
                team, pool = item
                code = (pool.competition_code or "").upper()
                tier = tier_by_code.get(code)
                tier_key = 999 if tier is None else tier
                name = (team.name or "").lower()
                state = by_comp.get(code)
                prev = (
                    state.previous_rows.get(team.id) if state is not None else None
                )
                in_opener = (
                    None
                    if state is None or state.opener_ids is None
                    else team.id in state.opener_ids
                )

                # Stayer: finished last season here and still in the new-year opener.
                if prev is not None and in_opener is not False:
                    return (
                        0,
                        tier_key,
                        1,
                        int(prev.rank),
                        -int(prev.points),
                        -int(prev.goal_difference),
                        -int(prev.goals_for),
                        name,
                    )

                # Relegated in: new to this competition, left a better-tier one.
                best: StandingsSnapshotRow | None = None
                best_other_tier: int | None = None
                for other_code, other_state in by_comp.items():
                    if other_code == code or team.id not in other_state.departed_ids:
                        continue
                    row = other_state.previous_rows.get(team.id)
                    if row is None:
                        continue
                    other_tier = tier_by_code.get(other_code)
                    if tier is None or other_tier is None or other_tier >= tier:
                        continue
                    if (
                        best is None
                        or other_tier < (best_other_tier or 999)
                        or (
                            other_tier == best_other_tier
                            and int(row.rank) < int(best.rank)
                        )
                    ):
                        best = row
                        best_other_tier = other_tier
                if best is not None:
                    return (
                        0,
                        tier_key,
                        0,
                        int(best.rank),
                        -int(best.points),
                        -int(best.goal_difference),
                        -int(best.goals_for),
                        name,
                    )

                # Promoted / newly added to this competition.
                return (0, tier_key, 2, 0, 0, 0, 0, name)

            return sorted(candidates, key=table_key), "table"

    return (
        sorted(candidates, key=lambda item: (item[0].name or "").lower()),
        "random",
    )


def select_autopick_team(
    db: Session,
    *,
    league: League,
    member: LeagueMember,
    pools: list[TeamPool],
    for_preview: bool = False,
) -> AutopickSelection | None:
    """Choose autopick team using fixed rankings or table baseline; else random."""
    candidates = _available_candidates(db, league=league, member=member, pools=pools)
    if not candidates:
        return None

    ordered, mode = sort_candidates_for_autopick(
        db, league=league, candidates=candidates
    )
    if mode == "random":
        if for_preview:
            return AutopickSelection(mode="random", team=None, pool=None)
        team, pool = random.choice(candidates)
        return AutopickSelection(mode="random", team=team, pool=pool)

    team, pool = ordered[0]
    return AutopickSelection(mode=mode, team=team, pool=pool)


def draft_order_by_team_pool(
    db: Session,
    *,
    league: League,
) -> dict[tuple[int, int], int]:
    """Map (team_id, pool_id) → 0-based autopick display order for the league.

    Order is stable for a given ranking/table snapshot; cached for the life of
    the draft (cleared on open/reset), not on a short TTL.
    """
    cached = _draft_order_cache.get(league.id)
    if cached is not None:
        return cached

    pools = list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all())
    if not pools:
        return {}
    pool_by_id = {p.id: p for p in pools}
    rows = db.execute(
        select(Team, PoolTeam.pool_id)
        .join(PoolTeam, PoolTeam.team_id == Team.id)
        .where(PoolTeam.pool_id.in_(pool_by_id.keys()))
    ).all()
    candidates: list[tuple[Team, TeamPool]] = []
    for team, pool_id in rows:
        pool = pool_by_id.get(int(pool_id))
        if pool is not None:
            candidates.append((team, pool))
    ordered, _ = sort_candidates_for_autopick(db, league=league, candidates=candidates)
    result = {
        (team.id, pool.id): index
        for index, (team, pool) in enumerate(ordered)
    }
    _draft_order_cache[league.id] = result
    return result


def _random_available_team(
    db: Session,
    *,
    league: League,
    member: LeagueMember,
    pools: list[TeamPool],
) -> tuple[Team, TeamPool] | None:
    """Backward-compatible helper; prefer ``select_autopick_team``."""
    selection = select_autopick_team(
        db, league=league, member=member, pools=pools, for_preview=False
    )
    if selection is None or selection.team is None or selection.pool is None:
        return None
    return selection.team, selection.pool


def make_pick(
    db: Session,
    *,
    league: League,
    picker_member: LeagueMember,
    team_public_id,
    pool_public_id=None,
    allow_commissioner_override: bool = False,
    allow_system_autopick: bool = False,
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
            state.pick_deadline_at = None
            db.flush()
            raise ConflictError("Draft completed — no open roster slots remain")
    else:
        raise ConflictError("Unable to find an on-clock manager with open slots")

    if expected.id != picker_member.id and not (
        allow_system_autopick
        or (allow_commissioner_override and picker_member.is_commissioner)
    ):
        raise ForbiddenError("It is not your turn")

    if allow_system_autopick or (
        allow_commissioner_override and picker_member.is_commissioner
    ):
        acting_member = expected
    else:
        acting_member = picker_member

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

    if pool_public_id is not None:
        pool = db.scalars(
            select(TeamPool).where(
                TeamPool.public_id == pool_public_id,
                TeamPool.league_id == league.id,
            )
        ).first()
        if pool is None:
            raise NotFoundError("Competition not found")
        pool_team = db.scalars(
            select(PoolTeam).where(
                PoolTeam.pool_id == pool.id,
                PoolTeam.team_id == team.id,
            )
        ).first()
        if pool_team is None:
            raise DomainError("Team is not in the selected competition")
    else:
        pool_team = db.scalars(
            select(PoolTeam)
            .join(TeamPool, TeamPool.id == PoolTeam.pool_id)
            .where(TeamPool.league_id == league.id, PoolTeam.team_id == team.id)
        ).first()
        if pool_team is None:
            raise DomainError("Team is not in any competition for this league")
        pool = db.get(TeamPool, pool_team.pool_id)
        if pool is None:
            raise NotFoundError("Competition not found")
    if member_pool_filled(db, acting_member.id, pool.id, pool.slot_count):
        raise ConflictError("Roster slot for this competition is full")

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
                state.pick_deadline_at = None
            else:
                apply_pick_deadline(state, league)
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
        logger.warning(
            "draft pick conflict league_id=%s pick_number=%s",
            log_id(league),
            state.current_pick_number,
        )
        raise ConflictError("Pick conflict (already taken or not your turn)") from exc

    logger.info(
        "draft pick made league_id=%s pick_number=%s round=%s member_id=%s team_id=%s autopick=%s",
        log_id(league),
        pick.pick_number,
        pick.round_number,
        log_id(acting_member),
        log_id(team),
        allow_system_autopick,
    )
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
        state.pick_deadline_at = None
    league.status = "pre_draft"
    # Clear schedule so a past draft_scheduled_at cannot auto-open again immediately.
    league.draft_scheduled_at = None
    invalidate_draft_order_cache(league.id)
    db.flush()
    logger.info("draft reset league_id=%s", log_id(league))
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
    apply_pick_deadline(state, league)
    db.flush()
    logger.info(
        "draft pick undone league_id=%s pick_number=%s team_id=%s",
        log_id(league),
        pick.pick_number,
        pick.team_id,
    )
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
                raise ConflictError(
                    "Destination manager has no open roster slots in this competition"
                )
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
            raise ConflictError("Replacement team is not in this competition")
        entry.team_id = new_team.id
        entry.source = "commissioner"
    db.flush()
    logger.info(
        "roster reassigned league_id=%s entry_id=%s member_id=%s team_id=%s",
        log_id(league),
        log_id(entry),
        entry.member_id,
        entry.team_id,
    )
    return entry


def ensure_draft_ranking_freeze(db: Session, league: League) -> bool:
    """Ensure fixed-rank leagues have a freeze snapshot for draft/autopick.

    Returns True when a freeze was newly attached (caller should commit).
    Idempotent if already frozen/locked.
    """
    rules = UpsetRules.from_config(league.upset_rules)
    if rules.rank_source != "fixed_ranking_at_event_start" or not rules.ranking_list_key:
        return False
    key = rules.ranking_list_key
    ranking_list = db.scalars(
        select(RankingList).where(
            RankingList.league_id == league.id,
            RankingList.key == key,
        )
    ).first()
    before = ranking_list.freeze_id if ranking_list is not None else None
    if before is not None:
        return False
    freeze_catalog_for_league_lock(db, league, key)
    invalidate_draft_order_cache(league.id)
    ranking_list = db.scalars(
        select(RankingList).where(
            RankingList.league_id == league.id,
            RankingList.key == key,
        )
    ).first()
    after = ranking_list.freeze_id if ranking_list is not None else None
    return after is not None


def open_draft(db: Session, league: League) -> DraftState:
    if league.status not in {"pre_draft", "drafting"}:
        raise ConflictError(f"Cannot open draft from league status {league.status}")
    readiness = evaluate_readiness(db, league, purpose="draft")
    if not readiness.ready:
        raise ConflictError(readiness.errors[0] if readiness.errors else "League is not ready")
    members = list(db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all())
    ordered = ordered_members(members)

    state = db.scalars(select(DraftState).where(DraftState.league_id == league.id)).first()
    if state is None:
        state = DraftState(league_id=league.id, current_pick_number=1, status="open")
        db.add(state)
    else:
        if state.status == "complete":
            raise ConflictError("Draft already complete")
        state.status = "open"
    league.status = "drafting"
    apply_pick_deadline(state, league)
    # Snap fixed rankings once so autopick/UI read freeze rows, not live catalog match.
    ensure_draft_ranking_freeze(db, league)
    invalidate_draft_order_cache(league.id)
    db.flush()
    logger.info(
        "draft opened league_id=%s managers=%s pick_timer_seconds=%s",
        log_id(league),
        len(ordered),
        league.pick_timer_seconds,
    )
    return state


def try_auto_open_if_scheduled(db: Session, league: League) -> bool:
    """Open draft when schedule is due and draft readiness passes. Returns True if opened."""
    if league.draft_scheduled_at is None or league.status != "pre_draft":
        return False
    if _aware(league.draft_scheduled_at) > datetime.now(UTC):
        return False
    state = db.scalars(select(DraftState).where(DraftState.league_id == league.id)).first()
    if state is not None and state.status != "pending":
        return False
    try:
        open_draft(db, league)
        logger.info("draft auto-opened league_id=%s", log_id(league))
        return True
    except ConflictError as exc:
        logger.info(
            "draft auto-open deferred league_id=%s reason=%s",
            log_id(league),
            getattr(exc, "message", str(exc)),
        )
        return False


def try_auto_pick_if_expired(db: Session, league: League) -> str:
    """Auto-pick when the pick clock has expired.

    Locks ``draft_state`` first so concurrent GET /draft polls (and cron) cannot
    race: only one writer selects+picks; waiters re-read and no-op once the
    deadline has advanced. Without this lock, failed races used to rewrite the
    *next* pick's deadline and look like broken live updates.

    Returns:
      "picked" — a pick was made
      "completed" — draft marked complete
      "deferred" — could not pick; deadline pushed forward
      "noop" — nothing to do
    """
    state = db.scalars(
        select(DraftState).where(DraftState.league_id == league.id).with_for_update()
    ).first()
    if state is None or state.status != "open" or state.pick_deadline_at is None:
        return "noop"
    if _aware(state.pick_deadline_at) > datetime.now(UTC):
        return "noop"
    if not league.pick_timer_seconds:
        return "noop"

    members = list(
        db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
    )
    pools = list(db.scalars(select(TeamPool).where(TeamPool.league_id == league.id)).all())
    try:
        ordered = ordered_members(members)
    except ConflictError as exc:
        logger.warning(
            "draft auto-pick skipped league_id=%s reason=%s",
            log_id(league),
            getattr(exc, "message", str(exc)),
        )
        return "noop"

    peeked = peek_on_clock_member(
        db, league=league, state=state, ordered=ordered, pools=pools
    )
    if peeked is None:
        if _draft_is_complete(db, league, ordered):
            state.status = "complete"
            league.status = "active"
            state.pick_deadline_at = None
            logger.info("draft auto-completed league_id=%s (no open slots)", log_id(league))
            return "completed"
        logger.warning("draft auto-pick no on-clock manager league_id=%s", log_id(league))
        # Avoid tight retry loops while the draft is stuck.
        apply_pick_deadline(state, league)
        return "deferred"

    on_clock, _ = peeked
    selection = select_autopick_team(
        db, league=league, member=on_clock, pools=pools, for_preview=False
    )
    if selection is None or selection.team is None or selection.pool is None:
        logger.warning(
            "draft auto-pick no available teams league_id=%s member_id=%s",
            log_id(league),
            log_id(on_clock),
        )
        # Push the clock forward so polls/cron do not hammer every few seconds.
        apply_pick_deadline(state, league)
        return "deferred"

    team, pool = selection.team, selection.pool
    try:
        make_pick(
            db,
            league=league,
            picker_member=on_clock,
            team_public_id=team.public_id,
            pool_public_id=pool.public_id,
            allow_system_autopick=True,
        )
        return "picked"
    except (ConflictError, ForbiddenError, DomainError, NotFoundError) as exc:
        logger.info(
            "draft auto-pick failed league_id=%s reason=%s",
            log_id(league),
            getattr(exc, "message", str(exc)),
        )
        # Only push the clock when it is still expired. Never rewrite a fresh
        # deadline another request already set for the next pick.
        db.refresh(state)
        if (
            state.status == "open"
            and state.pick_deadline_at is not None
            and _aware(state.pick_deadline_at) <= datetime.now(UTC)
        ):
            apply_pick_deadline(state, league)
            return "deferred"
        return "noop"


def enforce_league_draft_timers(db: Session, league: League) -> dict[str, int | bool]:
    """Auto-open if scheduled and catch up expired pick clocks for one league."""
    opened = try_auto_open_if_scheduled(db, league)
    auto_picks = 0
    changed = bool(opened)
    for _ in range(50):
        result = try_auto_pick_if_expired(db, league)
        if result == "noop":
            break
        changed = True
        if result == "picked":
            auto_picks += 1
            continue
        # completed or deferred — stop the catch-up loop
        break
    return {"opened": opened, "auto_picks": auto_picks, "changed": changed}


def run_draft_maintenance(db: Session) -> dict:
    """Cron: auto-open due drafts and auto-pick expired clocks across leagues."""
    now = datetime.now(UTC)
    due_open = list(
        db.scalars(
            select(League).where(
                League.draft_scheduled_at.is_not(None),
                League.draft_scheduled_at <= now,
                League.status == "pre_draft",
            )
        ).all()
    )
    expired_clock = list(
        db.scalars(
            select(League)
            .join(DraftState, DraftState.league_id == League.id)
            .where(
                DraftState.status == "open",
                DraftState.pick_deadline_at.is_not(None),
                DraftState.pick_deadline_at <= now,
            )
        ).all()
    )
    by_id: dict[int, League] = {league.id: league for league in due_open}
    for league in expired_clock:
        by_id[league.id] = league

    results: list[dict] = []
    for league in by_id.values():
        try:
            outcome = enforce_league_draft_timers(db, league)
            db.commit()
            results.append(
                {
                    "league_id": str(league.public_id),
                    "opened": bool(outcome["opened"]),
                    "auto_picks": int(outcome["auto_picks"]),
                }
            )
        except Exception:
            db.rollback()
            logger.exception(
                "draft maintenance failed league_id=%s",
                log_id(league),
            )
            results.append(
                {
                    "league_id": str(league.public_id),
                    "error": True,
                }
            )
    return {
        "ok": True,
        "leagues_considered": len(by_id),
        "results": results,
    }
