"""Pure scoring engine — unit-testable with no database.

Standings snapshots use finished matches with kickoff_at < this kickoff
(strict less-than so simultaneous kickoffs share one pre-kickoff table).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class Result(StrEnum):
    WIN = "win"
    DRAW = "draw"
    LOSS = "loss"
    WIN_ET = "win_et"
    LOSS_ET = "loss_et"
    WIN_PK = "win_pk"
    LOSS_PK = "loss_pk"


from app.services.match_constants import FINISHED_STATUSES

# Coarse outcomes used by competition tables and upset eligibility.
_WIN_RESULTS = frozenset({Result.WIN, Result.WIN_ET, Result.WIN_PK})
_LOSS_RESULTS = frozenset({Result.LOSS, Result.LOSS_ET, Result.LOSS_PK})


_STAGE_POINT_KEYS = ("win", "draw", "loss", "win_et", "loss_et", "win_pk", "loss_pk")


@dataclass(frozen=True)
class StageResultPoints:
    """Sparse per-stage overrides; None means use Default for that field."""

    win: Decimal | None = None
    draw: Decimal | None = None
    loss: Decimal | None = None
    win_et: Decimal | None = None
    loss_et: Decimal | None = None
    win_pk: Decimal | None = None
    loss_pk: Decimal | None = None

    def get(self, key: str) -> Decimal | None:
        return getattr(self, key, None)

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> StageResultPoints:
        cfg = dict(config or {})
        kwargs: dict[str, Decimal | None] = {}
        for key in _STAGE_POINT_KEYS:
            if key in cfg and cfg[key] is not None and cfg[key] != "":
                kwargs[key] = Decimal(str(cfg[key]))
        return cls(**kwargs)


@dataclass(frozen=True)
class ResultPoints:
    win: Decimal = Decimal(3)
    draw: Decimal = Decimal(1)
    loss: Decimal = Decimal(0)
    # None = inherit from Default win/loss.
    win_et: Decimal | None = None
    loss_et: Decimal | None = None
    win_pk: Decimal | None = None
    loss_pk: Decimal | None = None
    by_stage: Mapping[str, StageResultPoints] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> ResultPoints:
        cfg = dict(config or {})
        win = Decimal(str(cfg.get("win", 3)))
        draw = Decimal(str(cfg.get("draw", 1)))
        loss = Decimal(str(cfg.get("loss", 0)))
        by_stage_raw = cfg.get("by_stage")
        by_stage: dict[str, StageResultPoints] = {}
        if isinstance(by_stage_raw, Mapping):
            for stage_key, stage_cfg in by_stage_raw.items():
                code = str(stage_key).strip()
                if not code or not isinstance(stage_cfg, Mapping):
                    continue
                parsed = StageResultPoints.from_config(stage_cfg)
                if any(parsed.get(k) is not None for k in _STAGE_POINT_KEYS):
                    by_stage[code] = parsed
        return cls(
            win=win,
            draw=draw,
            loss=loss,
            win_et=Decimal(str(cfg["win_et"])) if "win_et" in cfg else None,
            loss_et=Decimal(str(cfg["loss_et"])) if "loss_et" in cfg else None,
            win_pk=Decimal(str(cfg["win_pk"])) if "win_pk" in cfg else None,
            loss_pk=Decimal(str(cfg["loss_pk"])) if "loss_pk" in cfg else None,
            by_stage=by_stage,
        )


@dataclass(frozen=True)
class UpsetThreshold:
    key: str
    result: Result
    min_gap: int
    max_gap: int | None
    points: Decimal
    name: str = ""

    def matches(self, result: Result, gap: int) -> bool:
        if self.result is not result or gap < self.min_gap:
            return False
        if self.max_gap is not None and gap > self.max_gap:
            return False
        return True


@dataclass(frozen=True)
class UpsetRules:
    enabled: bool = True
    rank_source: str = "league_table_at_kickoff"
    ranking_list_key: str | None = None
    min_played: int = 8
    thresholds: tuple[UpsetThreshold, ...] = ()

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> UpsetRules:
        cfg = dict(config or {})
        eligibility = cfg.get("eligibility") or {}
        min_played = int(eligibility.get("min_played", cfg.get("min_played", 8)))
        thresholds: list[UpsetThreshold] = []
        for item in cfg.get("thresholds") or []:
            key = str(item["key"])
            name = str(item.get("name") or key)
            thresholds.append(
                UpsetThreshold(
                    key=key,
                    result=Result(str(item["result"])),
                    min_gap=int(item.get("min_gap", 0)),
                    max_gap=None if item.get("max_gap") is None else int(item["max_gap"]),
                    points=Decimal(str(item.get("points", 0))),
                    name=name,
                )
            )
        return cls(
            enabled=bool(cfg.get("enabled", True)),
            rank_source=str(cfg.get("rank_source", "league_table_at_kickoff")),
            ranking_list_key=cfg.get("ranking_list_key"),
            min_played=min_played,
            thresholds=tuple(thresholds),
        )


PL_DEFAULT_UPSET_RULES = UpsetRules.from_config(
    {
        "enabled": True,
        "rank_source": "league_table_at_kickoff",
        "eligibility": {"min_played": 8},
        "thresholds": [
            {
                "key": "minor_upset",
                "name": "Minor upset",
                "min_gap": 5,
                "max_gap": 9,
                "result": "win",
                "points": 1,
            },
            {
                "key": "major_upset",
                "name": "Major upset",
                "min_gap": 10,
                "max_gap": None,
                "result": "win",
                "points": 3,
            },
            {
                "key": "major_upset_draw",
                "name": "Major upset draw",
                "min_gap": 10,
                "max_gap": None,
                "result": "draw",
                "points": 1,
            },
        ],
    }
)


@dataclass(frozen=True)
class TableRow:
    team_id: int
    name: str = ""
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0

    @property
    def gd(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def gf(self) -> int:
        return self.goals_for

    @property
    def goal_difference(self) -> int:
        return self.gd


@dataclass(frozen=True)
class RankedTeam:
    team_id: int
    rank: int
    played: int
    points: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    name: str = ""


@dataclass(frozen=True)
class MatchInput:
    match_id: int
    pool_id: int
    home_team_id: int
    away_team_id: int
    kickoff_at: datetime
    home_goals: int | None
    away_goals: int | None
    status: str = "FINISHED"
    duration: str = "REGULAR"
    scheduled_matchweek: int | None = None
    stage: str | None = None


@dataclass(frozen=True)
class ScoringEventDraft:
    match_id: int
    team_id: int
    event_type: str
    points: Decimal
    scheduled_matchweek: int | None = None
    stage: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LeaderboardRung:
    metric: str
    direction: str = "desc"
    event_types: tuple[str, ...] = ()
    bonus_type_keys: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, item: Mapping[str, Any]) -> LeaderboardRung:
        return cls(
            metric=str(item["metric"]),
            direction=str(item.get("direction", "desc")),
            event_types=tuple(item.get("event_types") or ()),
            bonus_type_keys=tuple(item.get("bonus_type_keys") or ()),
        )


@dataclass(frozen=True)
class MemberPoints:
    member_id: int
    total_points: Decimal
    event_points_by_type: Mapping[str, Decimal] = field(default_factory=dict)
    event_counts_by_type: Mapping[str, int] = field(default_factory=dict)
    bonus_points_by_type: Mapping[str, Decimal] = field(default_factory=dict)
    bonus_counts_by_type: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RankedLeaderboardEntry:
    rank: int
    member_id: int
    total_points: Decimal
    rung_values: tuple[Decimal | int, ...]


@dataclass(frozen=True)
class RecomputePlan:
    changed_match_id: int
    pool_id: int
    starts_at: datetime
    stale_kickoffs: tuple[datetime, ...]
    affected_match_ids: tuple[int, ...]
    reason: str


DEFAULT_TABLE_TIEBREAKS = ("points", "gd", "gf", "name")


def result_for(goals_for: int, goals_against: int) -> Result:
    """Competition-table outcome from goals (ignores duration)."""
    if goals_for > goals_against:
        return Result.WIN
    if goals_for < goals_against:
        return Result.LOSS
    return Result.DRAW


def fantasy_result_for(
    goals_for: int, goals_against: int, duration: str = "REGULAR"
) -> Result:
    """Fantasy outcome keyed by match duration (REGULAR / EXTRA_TIME / PENALTY_SHOOTOUT)."""
    base = result_for(goals_for, goals_against)
    if duration == "EXTRA_TIME":
        if base is Result.WIN:
            return Result.WIN_ET
        if base is Result.LOSS:
            return Result.LOSS_ET
        # Drawn after ET should not happen (would go to PKs); treat as draw.
        return Result.DRAW
    if duration == "PENALTY_SHOOTOUT":
        if base is Result.WIN:
            return Result.WIN_PK
        if base is Result.LOSS:
            return Result.LOSS_PK
        return Result.DRAW
    return base


def coarse_result(result: Result) -> Result:
    """Map ET/PK results to win/draw/loss for upset eligibility."""
    if result in _WIN_RESULTS:
        return Result.WIN
    if result in _LOSS_RESULTS:
        return Result.LOSS
    return Result.DRAW


def _default_points_for_result(result: Result, points: ResultPoints) -> Decimal:
    """Points from the Default block only (ET/PK inherit Default win/loss)."""
    if result is Result.WIN:
        return points.win
    if result is Result.DRAW:
        return points.draw
    if result is Result.LOSS:
        return points.loss
    if result is Result.WIN_ET:
        return points.win_et if points.win_et is not None else points.win
    if result is Result.LOSS_ET:
        return points.loss_et if points.loss_et is not None else points.loss
    if result is Result.WIN_PK:
        return points.win_pk if points.win_pk is not None else points.win
    if result is Result.LOSS_PK:
        return points.loss_pk if points.loss_pk is not None else points.loss
    return points.draw


def points_for_result(
    result: Result,
    points: ResultPoints,
    stage: str | None = None,
) -> Decimal:
    """Resolve fantasy points for a result, optionally scoped to a match stage.

    Stage sparse overrides win when set; any empty stage field always uses Default
    for that same result type (Default ET/PK still inherit Default win/loss).
    """
    if stage:
        stage_pts = points.by_stage.get(stage)
        if stage_pts is not None:
            stage_val = stage_pts.get(result.value)
            if stage_val is not None:
                return stage_val
    return _default_points_for_result(result, points)


def normalize_tiebreaks(tiebreaks: Sequence[str] | None) -> tuple[str, ...]:
    allowed = {"points", "gd", "gf", "name"}
    ordered = tuple(tiebreaks or DEFAULT_TABLE_TIEBREAKS)
    unknown = set(ordered) - allowed
    if unknown:
        raise ValueError(f"unsupported table tiebreaks: {sorted(unknown)}")
    return ordered or DEFAULT_TABLE_TIEBREAKS


def rank_table(
    rows: Iterable[TableRow],
    tiebreaks: Sequence[str] = DEFAULT_TABLE_TIEBREAKS,
) -> tuple[RankedTeam, ...]:
    keys = normalize_tiebreaks(tiebreaks)

    def sort_key(row: TableRow) -> tuple[object, ...]:
        values: list[object] = []
        for field_name in keys:
            value = getattr(row, field_name)
            values.append(value if field_name == "name" else -value)
        values.append(row.team_id)
        return tuple(values)

    ranked = sorted(rows, key=sort_key)
    return tuple(
        RankedTeam(
            team_id=row.team_id,
            rank=index,
            played=row.played,
            points=row.points,
            goals_for=row.goals_for,
            goals_against=row.goals_against,
            goal_difference=row.gd,
            name=row.name,
        )
        for index, row in enumerate(ranked, start=1)
    )


def _apply_result(row: TableRow, goals_for: int, goals_against: int, points: ResultPoints) -> TableRow:
    result = result_for(goals_for, goals_against)
    return replace(
        row,
        played=row.played + 1,
        wins=row.wins + (result is Result.WIN),
        draws=row.draws + (result is Result.DRAW),
        losses=row.losses + (result is Result.LOSS),
        goals_for=row.goals_for + goals_for,
        goals_against=row.goals_against + goals_against,
        points=row.points + int(points_for_result(result, points)),
    )


def is_finished(match: MatchInput) -> bool:
    return (
        match.status in FINISHED_STATUSES
        and match.home_goals is not None
        and match.away_goals is not None
    )


def build_standings_before_kickoff(
    *,
    team_rows: Iterable[TableRow],
    finished_matches: Iterable[MatchInput],
    kickoff_at: datetime,
    pool_id: int | None = None,
    result_points: ResultPoints | None = None,
    tiebreaks: Sequence[str] = DEFAULT_TABLE_TIEBREAKS,
) -> tuple[RankedTeam, ...]:
    """Table from finished matches with kickoff_at < this kickoff (strict)."""
    points = result_points or ResultPoints()
    rows = {row.team_id: row for row in team_rows}
    prior = [
        match
        for match in finished_matches
        if is_finished(match)
        and match.kickoff_at < kickoff_at
        and (pool_id is None or match.pool_id == pool_id)
    ]
    prior.sort(key=lambda m: (m.kickoff_at, m.match_id))
    for match in prior:
        rows[match.home_team_id] = _apply_result(
            rows[match.home_team_id], match.home_goals, match.away_goals, points
        )
        rows[match.away_team_id] = _apply_result(
            rows[match.away_team_id], match.away_goals, match.home_goals, points
        )
    return rank_table(rows.values(), tiebreaks)


def kickoff_snapshots(
    matches: Iterable[MatchInput],
    initial_rows: Iterable[TableRow],
    *,
    result_points: ResultPoints | None = None,
    tiebreaks: Sequence[str] = DEFAULT_TABLE_TIEBREAKS,
) -> dict[datetime, tuple[RankedTeam, ...]]:
    """One snapshot per distinct kickoff time (shared by simultaneous matches)."""
    points = result_points or ResultPoints()
    finished = [m for m in matches if is_finished(m)]
    kickoffs = sorted({m.kickoff_at for m in finished})
    return {
        kickoff: build_standings_before_kickoff(
            team_rows=initial_rows,
            finished_matches=finished,
            kickoff_at=kickoff,
            result_points=points,
            tiebreaks=tiebreaks,
        )
        for kickoff in kickoffs
    }


def snapshot_map(snapshot: Sequence[RankedTeam]) -> dict[int, RankedTeam]:
    return {row.team_id: row for row in snapshot}


def upset_bonus(
    underdog: RankedTeam,
    opponent: RankedTeam,
    result: Result,
    rules: UpsetRules,
) -> tuple[Decimal, str | None, int]:
    """Return (points, threshold_key, gap). Gap = underdog_rank - opponent_rank."""
    if not rules.enabled:
        return Decimal(0), None, 0
    if underdog.played < rules.min_played or opponent.played < rules.min_played:
        return Decimal(0), None, 0
    gap = underdog.rank - opponent.rank
    if gap <= 0:
        return Decimal(0), None, gap
    matched = [t for t in rules.thresholds if t.matches(result, gap)]
    if len(matched) > 1:
        raise ValueError("multiple upset thresholds matched")
    if not matched:
        return Decimal(0), None, gap
    return matched[0].points, matched[0].key, gap


def score_match_events(
    match: MatchInput,
    snapshot: Mapping[int, RankedTeam],
    *,
    result_points: ResultPoints,
    upset_rules: UpsetRules,
) -> tuple[ScoringEventDraft, ...]:
    if not is_finished(match):
        return ()
    home = snapshot[match.home_team_id]
    away = snapshot[match.away_team_id]
    assert match.home_goals is not None and match.away_goals is not None
    home_result = fantasy_result_for(match.home_goals, match.away_goals, match.duration)
    away_result = fantasy_result_for(match.away_goals, match.home_goals, match.duration)
    home_coarse = coarse_result(home_result)
    away_coarse = coarse_result(away_result)
    events: list[ScoringEventDraft] = []

    def add_result(team_id: int, result: Result) -> None:
        pts = points_for_result(result, result_points, match.stage)
        # Skip zero-point outcomes (typically losses) so leaderboards stay clean.
        if pts == 0:
            return
        events.append(
            ScoringEventDraft(
                match_id=match.match_id,
                team_id=team_id,
                event_type=result.value,
                points=pts,
                scheduled_matchweek=match.scheduled_matchweek,
                stage=match.stage,
                metadata={
                    "home_rank": home.rank,
                    "away_rank": away.rank,
                    "home_played": home.played,
                    "away_played": away.played,
                    "duration": match.duration,
                },
            )
        )

    add_result(match.home_team_id, home_result)
    add_result(match.away_team_id, away_result)

    if home_coarse is Result.WIN:
        bonus, key, gap = upset_bonus(home, away, Result.WIN, upset_rules)
        if key and bonus:
            logger.debug(
                "upset bonus match_id=%s team_id=%s event_type=%s points=%s gap=%s",
                match.match_id,
                match.home_team_id,
                key,
                bonus,
                gap,
            )
            events.append(
                ScoringEventDraft(
                    match_id=match.match_id,
                    team_id=match.home_team_id,
                    event_type=key,
                    points=bonus,
                    scheduled_matchweek=match.scheduled_matchweek,
                    stage=match.stage,
                    metadata={
                        "gap": gap,
                        "underdog_rank": home.rank,
                        "opponent_rank": away.rank,
                        "rank_source": upset_rules.rank_source,
                    },
                )
            )
    elif away_coarse is Result.WIN:
        bonus, key, gap = upset_bonus(away, home, Result.WIN, upset_rules)
        if key and bonus:
            logger.debug(
                "upset bonus match_id=%s team_id=%s event_type=%s points=%s gap=%s",
                match.match_id,
                match.away_team_id,
                key,
                bonus,
                gap,
            )
            events.append(
                ScoringEventDraft(
                    match_id=match.match_id,
                    team_id=match.away_team_id,
                    event_type=key,
                    points=bonus,
                    scheduled_matchweek=match.scheduled_matchweek,
                    stage=match.stage,
                    metadata={
                        "gap": gap,
                        "underdog_rank": away.rank,
                        "opponent_rank": home.rank,
                        "rank_source": upset_rules.rank_source,
                    },
                )
            )
    else:
        underdog, opponent = (home, away) if home.rank > away.rank else (away, home)
        bonus, key, gap = upset_bonus(underdog, opponent, Result.DRAW, upset_rules)
        if key and bonus:
            logger.debug(
                "upset bonus match_id=%s team_id=%s event_type=%s points=%s gap=%s",
                match.match_id,
                underdog.team_id,
                key,
                bonus,
                gap,
            )
            events.append(
                ScoringEventDraft(
                    match_id=match.match_id,
                    team_id=underdog.team_id,
                    event_type=key,
                    points=bonus,
                    scheduled_matchweek=match.scheduled_matchweek,
                    stage=match.stage,
                    metadata={
                        "gap": gap,
                        "underdog_rank": underdog.rank,
                        "opponent_rank": opponent.rank,
                        "rank_source": upset_rules.rank_source,
                    },
                )
            )
    return tuple(events)


def plan_recompute_cascade(
    changed_match: MatchInput,
    all_matches: Iterable[MatchInput],
) -> RecomputePlan:
    """Mark snapshots with kickoff_at > changed kickoff stale; re-score from that kickoff."""
    same_pool = [
        m for m in all_matches if m.pool_id == changed_match.pool_id and is_finished(m)
    ]
    # Preserve kickoff order for affected ids
    ordered = sorted(
        (m for m in same_pool if m.kickoff_at >= changed_match.kickoff_at),
        key=lambda m: (m.kickoff_at, m.match_id),
    )
    affected = tuple(m.match_id for m in ordered)
    stale_kickoffs = tuple(sorted({m.kickoff_at for m in ordered if m.kickoff_at > changed_match.kickoff_at}))
    logger.debug(
        "plan_recompute_cascade changed_match_id=%s pool_id=%s affected=%s stale_kickoffs=%s",
        changed_match.match_id,
        changed_match.pool_id,
        len(affected),
        len(stale_kickoffs),
    )
    return RecomputePlan(
        changed_match_id=changed_match.match_id,
        pool_id=changed_match.pool_id,
        starts_at=changed_match.kickoff_at,
        stale_kickoffs=stale_kickoffs,
        affected_match_ids=affected,
        reason=(
            "result correction invalidates later kickoff snapshots in the same pool "
            "and requires re-deriving scoring_events from this kickoff forward"
        ),
    )


def match_passes_phase_filter(
    *,
    scheduled_matchweek: int | None,
    stage: str | None,
    match_filter: Mapping[str, Any] | None,
) -> bool:
    if not match_filter:
        return True
    filter_type = match_filter.get("type")
    if filter_type == "matchweek_range":
        if scheduled_matchweek is None:
            return False
        return int(match_filter["from"]) <= scheduled_matchweek <= int(match_filter["to"])
    if filter_type == "stage_in":
        stages = set(match_filter.get("stages") or [])
        return stage in stages
    raise ValueError(f"unsupported phase match_filter type: {filter_type}")


def phase_points_from_events(
    events: Iterable[Mapping[str, Any]],
    match_filter: Mapping[str, Any] | None,
) -> Decimal:
    total = Decimal(0)
    for event in events:
        if match_passes_phase_filter(
            scheduled_matchweek=event.get("scheduled_matchweek"),
            stage=event.get("stage"),
            match_filter=match_filter,
        ):
            total += Decimal(str(event["points"]))
    return total


def rank_leaderboard(
    members: Iterable[MemberPoints],
    tiebreaks: Sequence[Mapping[str, Any] | LeaderboardRung],
) -> tuple[RankedLeaderboardEntry, ...]:
    rungs = tuple(
        item if isinstance(item, LeaderboardRung) else LeaderboardRung.from_config(item)
        for item in tiebreaks
    )
    if not rungs:
        raise ValueError("leaderboard requires at least one metric rung")

    def rung_value(member: MemberPoints, rung: LeaderboardRung) -> Decimal | int:
        if rung.metric == "total_points":
            return member.total_points
        if rung.metric == "event_points":
            return sum(
                (member.event_points_by_type.get(key, Decimal(0)) for key in rung.event_types),
                Decimal(0),
            )
        if rung.metric == "event_count":
            return sum(member.event_counts_by_type.get(key, 0) for key in rung.event_types)
        if rung.metric == "bonus_points":
            return sum(
                (member.bonus_points_by_type.get(key, Decimal(0)) for key in rung.bonus_type_keys),
                Decimal(0),
            )
        if rung.metric == "bonus_count":
            return sum(member.bonus_counts_by_type.get(key, 0) for key in rung.bonus_type_keys)
        raise ValueError(f"unsupported leaderboard metric: {rung.metric}")

    def sort_key(member: MemberPoints) -> tuple[Decimal | int, ...]:
        values = []
        for rung in rungs:
            value = rung_value(member, rung)
            values.append(-value if rung.direction == "desc" else value)
        return tuple(values)

    ordered = sorted(members, key=sort_key)
    ranked: list[RankedLeaderboardEntry] = []
    previous_key: tuple[Decimal | int, ...] | None = None
    previous_rank = 0
    for ordinal, member in enumerate(ordered, start=1):
        key = sort_key(member)
        rank = previous_rank if key == previous_key else ordinal
        values = tuple(rung_value(member, rung) for rung in rungs)
        ranked.append(
            RankedLeaderboardEntry(
                rank=rank,
                member_id=member.member_id,
                total_points=member.total_points,
                rung_values=values,
            )
        )
        previous_key = key
        previous_rank = rank
    return tuple(ranked)


def attribute_team_points_to_members(
    team_points: Mapping[int, Decimal],
    roster: Mapping[int, int],
) -> dict[int, Decimal]:
    """roster maps team_id -> member_id. Points are keyed by team, not member."""
    totals: dict[int, Decimal] = defaultdict(lambda: Decimal(0))
    for team_id, points in team_points.items():
        member_id = roster.get(team_id)
        if member_id is not None:
            totals[member_id] += points
    return dict(totals)
