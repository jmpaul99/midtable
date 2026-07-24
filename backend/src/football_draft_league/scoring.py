from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class Result(StrEnum):
    WIN = "win"
    DRAW = "draw"
    LOSS = "loss"


@dataclass(frozen=True)
class ResultPoints:
    win: Decimal = Decimal(3)
    draw: Decimal = Decimal(1)
    loss: Decimal = Decimal(0)


@dataclass(frozen=True, order=True)
class UpsetThreshold:
    result: Result
    minimum_position_gap: int
    maximum_position_gap: int | None
    bonus: Decimal

    def __post_init__(self) -> None:
        if self.minimum_position_gap < 1:
            raise ValueError("minimum_position_gap must be positive")
        if (
            self.maximum_position_gap is not None
            and self.maximum_position_gap < self.minimum_position_gap
        ):
            raise ValueError("maximum_position_gap cannot be below the minimum")

    def matches(self, result: Result, position_gap: int) -> bool:
        return (
            self.result is result
            and position_gap >= self.minimum_position_gap
            and (
                self.maximum_position_gap is None
                or position_gap <= self.maximum_position_gap
            )
        )


@dataclass(frozen=True)
class UpsetRules:
    thresholds: tuple[UpsetThreshold, ...] = ()
    minimum_matches_played: int = 8

    def __post_init__(self) -> None:
        if self.minimum_matches_played < 0:
            raise ValueError("minimum_matches_played cannot be negative")
        for result in Result:
            result_rules = sorted(
                (rule for rule in self.thresholds if rule.result is result),
                key=lambda rule: rule.minimum_position_gap,
            )
            for previous, current in zip(result_rules, result_rules[1:], strict=False):
                if (
                    previous.maximum_position_gap is None
                    or previous.maximum_position_gap >= current.minimum_position_gap
                ):
                    raise ValueError(f"overlapping upset thresholds for {result}")


@dataclass(frozen=True)
class ScoringPhase:
    name: str
    first_matchweek: int
    last_matchweek: int
    result_points: ResultPoints = ResultPoints()
    upset_rules: UpsetRules = UpsetRules()

    def __post_init__(self) -> None:
        if self.first_matchweek < 1 or self.last_matchweek < self.first_matchweek:
            raise ValueError("invalid matchweek phase bounds")

    def contains(self, matchweek: int) -> bool:
        return self.first_matchweek <= matchweek <= self.last_matchweek


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
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


@dataclass(frozen=True)
class PositionedTeam:
    team_id: int
    position: int
    played: int


@dataclass(frozen=True)
class MatchResult:
    match_id: int
    competition_id: int
    home_team_id: int
    away_team_id: int
    kickoff_at: datetime
    matchweek: int
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class TeamScore:
    team_id: int
    result: Result
    result_points: Decimal
    upset_bonus: Decimal
    phase: str

    @property
    def total(self) -> Decimal:
        return self.result_points + self.upset_bonus


@dataclass(frozen=True)
class LeaderboardEntry:
    member_id: int
    total_points: Decimal
    upset_points: Decimal = Decimal(0)
    win_count: int = 0
    rung_values: tuple[Decimal | int, ...] = ()


@dataclass(frozen=True)
class LeaderboardRung:
    metric: str
    event_types: tuple[str, ...] = ()
    bonus_type_keys: tuple[str, ...] = ()
    direction: str = "desc"

    def __post_init__(self) -> None:
        supported = {
            "total_points",
            "event_points",
            "event_count",
            "bonus_points",
            "bonus_count",
        }
        if self.metric not in supported:
            raise ValueError(f"unsupported leaderboard metric: {self.metric}")
        if self.direction not in {"desc", "asc"}:
            raise ValueError("leaderboard direction must be desc or asc")
        if (self.metric in {"event_points", "event_count"}) != bool(self.event_types):
            raise ValueError("event metric selectors are invalid")
        if (self.metric in {"bonus_points", "bonus_count"}) != bool(self.bonus_type_keys):
            raise ValueError("bonus metric selectors are invalid")


@dataclass(frozen=True)
class RankedLeaderboardEntry:
    rank: int
    entry: LeaderboardEntry


@dataclass(frozen=True)
class ManualBonusDefaults:
    winner: Decimal = Decimal(12)
    champions_league: Decimal = Decimal(9)
    other_europe: Decimal = Decimal(6)
    championship_promotion: Decimal = Decimal(20)
    relegation: Decimal = Decimal(-10)


DEFAULT_MANUAL_BONUSES = ManualBonusDefaults()
DEFAULT_TABLE_TIEBREAKS = ("points", "goal_difference", "goals_for", "name")
DEFAULT_LEADERBOARD_RUNGS = (
    LeaderboardRung("total_points"),
    LeaderboardRung("event_points", ("upset",)),
    LeaderboardRung("event_count", ("win",)),
)


@dataclass(frozen=True)
class RecomputePlan:
    corrected_match_id: int
    affected_match_ids: tuple[int, ...]
    starts_at: datetime
    reason: str


def result_for(goals_for: int, goals_against: int) -> Result:
    if goals_for > goals_against:
        return Result.WIN
    if goals_for < goals_against:
        return Result.LOSS
    return Result.DRAW


def points_for_result(result: Result, points: ResultPoints) -> Decimal:
    return {
        Result.WIN: points.win,
        Result.DRAW: points.draw,
        Result.LOSS: points.loss,
    }[result]


def upset_bonus(
    underdog: PositionedTeam,
    opponent: PositionedTeam,
    result: Result,
    rules: UpsetRules,
) -> Decimal:
    """Score an underdog result against the pre-kickoff table snapshot."""
    if (
        underdog.played < rules.minimum_matches_played
        or opponent.played < rules.minimum_matches_played
    ):
        return Decimal(0)
    position_gap = underdog.position - opponent.position
    if position_gap <= 0:
        return Decimal(0)
    matched = [
        threshold.bonus
        for threshold in rules.thresholds
        if threshold.matches(result, position_gap)
    ]
    if len(matched) > 1:
        raise ValueError("multiple upset thresholds matched")
    return matched[0] if matched else Decimal(0)


def phase_for(matchweek: int, phases: Sequence[ScoringPhase]) -> ScoringPhase:
    matches = [phase for phase in phases if phase.contains(matchweek)]
    if len(matches) != 1:
        raise ValueError(f"matchweek must belong to exactly one scoring phase, got {len(matches)}")
    return matches[0]


def score_match(
    match: MatchResult,
    snapshot: Mapping[int, PositionedTeam],
    phase: ScoringPhase,
) -> tuple[TeamScore, TeamScore]:
    if not phase.contains(match.matchweek):
        raise ValueError(f"matchweek {match.matchweek} is outside phase {phase.name}")
    home_result = result_for(match.home_goals, match.away_goals)
    away_result = result_for(match.away_goals, match.home_goals)
    bonuses = {match.home_team_id: Decimal(0), match.away_team_id: Decimal(0)}
    if home_result is Result.WIN:
        bonuses[match.home_team_id] = upset_bonus(
            snapshot[match.home_team_id],
            snapshot[match.away_team_id],
            home_result,
            phase.upset_rules,
        )
    elif away_result is Result.WIN:
        bonuses[match.away_team_id] = upset_bonus(
            snapshot[match.away_team_id],
            snapshot[match.home_team_id],
            away_result,
            phase.upset_rules,
        )
    else:
        home = snapshot[match.home_team_id]
        away = snapshot[match.away_team_id]
        underdog, opponent = (home, away) if home.position > away.position else (away, home)
        bonuses[underdog.team_id] = upset_bonus(
            underdog, opponent, Result.DRAW, phase.upset_rules
        )
    return (
        TeamScore(
            match.home_team_id,
            home_result,
            points_for_result(home_result, phase.result_points),
            bonuses[match.home_team_id],
            phase.name,
        ),
        TeamScore(
            match.away_team_id,
            away_result,
            points_for_result(away_result, phase.result_points),
            bonuses[match.away_team_id],
            phase.name,
        ),
    )


def rank_table(
    rows: Iterable[TableRow],
    tiebreaks: Sequence[str] = DEFAULT_TABLE_TIEBREAKS,
) -> tuple[TableRow, ...]:
    supported = {"points", "goal_difference", "goals_for", "name"}
    if unknown := set(tiebreaks) - supported:
        raise ValueError(f"unsupported table tiebreaks: {sorted(unknown)}")

    def key(row: TableRow) -> tuple[object, ...]:
        values: list[object] = []
        for field in tiebreaks:
            value = getattr(row, field)
            values.append(value if field == "name" else -value)
        values.append(row.team_id)
        return tuple(values)

    return tuple(sorted(rows, key=key))


def _apply(row: TableRow, goals_for: int, goals_against: int) -> TableRow:
    result = result_for(goals_for, goals_against)
    return replace(
        row,
        played=row.played + 1,
        wins=row.wins + (result is Result.WIN),
        draws=row.draws + (result is Result.DRAW),
        losses=row.losses + (result is Result.LOSS),
        goals_for=row.goals_for + goals_for,
        goals_against=row.goals_against + goals_against,
        points=row.points + int(points_for_result(result, ResultPoints())),
    )


def kickoff_snapshots(
    matches: Iterable[MatchResult],
    initial_rows: Iterable[TableRow],
    tiebreaks: Sequence[str] = DEFAULT_TABLE_TIEBREAKS,
) -> tuple[dict[int, dict[int, PositionedTeam]], tuple[TableRow, ...]]:
    """Build pre-kickoff snapshots; equal kickoff times share one snapshot."""
    rows = {row.team_id: row for row in initial_rows}
    groups: dict[datetime, list[MatchResult]] = defaultdict(list)
    for match in matches:
        groups[match.kickoff_at].append(match)

    snapshots: dict[int, dict[int, PositionedTeam]] = {}
    for kickoff_at in sorted(groups):
        ranked = rank_table(rows.values(), tiebreaks)
        snapshot = {
            row.team_id: PositionedTeam(row.team_id, position, row.played)
            for position, row in enumerate(ranked, start=1)
        }
        for match in groups[kickoff_at]:
            snapshots[match.match_id] = snapshot.copy()
        for match in groups[kickoff_at]:
            rows[match.home_team_id] = _apply(
                rows[match.home_team_id], match.home_goals, match.away_goals
            )
            rows[match.away_team_id] = _apply(
                rows[match.away_team_id], match.away_goals, match.home_goals
            )
    return snapshots, rank_table(rows.values(), tiebreaks)


def rank_leaderboard(
    entries: Iterable[LeaderboardEntry],
    metric_rungs: Sequence[str | LeaderboardRung] = DEFAULT_LEADERBOARD_RUNGS,
) -> tuple[RankedLeaderboardEntry, ...]:
    legacy = {
        "total_points": LeaderboardRung("total_points"),
        "upset_points": LeaderboardRung("event_points", ("upset",)),
        "win_count": LeaderboardRung("event_count", ("win",)),
    }
    try:
        rungs = tuple(legacy[item] if isinstance(item, str) else item for item in metric_rungs)
    except KeyError as exc:
        raise ValueError(f"unsupported leaderboard metric rung: {exc.args[0]}") from exc
    if not rungs:
        raise ValueError("leaderboard requires at least one metric rung")
    if len(rungs) != len(set(rungs)):
        raise ValueError("leaderboard metric rungs cannot repeat")

    def rung_value(entry: LeaderboardEntry, rung: LeaderboardRung, index: int) -> Decimal | int:
        if entry.rung_values:
            if len(entry.rung_values) != len(rungs):
                raise ValueError("entry rung value count does not match configured rungs")
            return entry.rung_values[index]
        if rung.metric == "total_points":
            return entry.total_points
        if rung.metric == "event_points" and rung.event_types == ("upset",):
            return entry.upset_points
        if rung.metric == "event_count" and rung.event_types == ("win",):
            return entry.win_count
        raise ValueError("structured rungs require precomputed entry rung_values")

    def key(entry: LeaderboardEntry) -> tuple[Decimal | int, ...]:
        values = (rung_value(entry, rung, index) for index, rung in enumerate(rungs))
        return tuple(-value if rung.direction == "desc" else value for value, rung in zip(values, rungs))

    ordered = sorted(entries, key=key)
    ranked: list[RankedLeaderboardEntry] = []
    previous_key: tuple[Decimal | int, ...] | None = None
    previous_rank = 0
    for ordinal, entry in enumerate(ordered, start=1):
        entry_key = key(entry)
        rank = previous_rank if entry_key == previous_key else ordinal
        ranked.append(RankedLeaderboardEntry(rank, entry))
        previous_key = entry_key
        previous_rank = rank
    return tuple(ranked)


def plan_result_correction(
    corrected_match_id: int,
    matches: Iterable[MatchResult],
) -> RecomputePlan:
    ordered = sorted(matches, key=lambda match: (match.kickoff_at, match.match_id))
    corrected = next((match for match in ordered if match.match_id == corrected_match_id), None)
    if corrected is None:
        raise ValueError("corrected match is not present")
    affected = tuple(
        match.match_id
        for match in ordered
        if match.competition_id == corrected.competition_id
        and match.kickoff_at >= corrected.kickoff_at
    )
    return RecomputePlan(
        corrected_match_id,
        affected,
        corrected.kickoff_at,
        "result correction changes all same-competition kickoff snapshots from this time",
    )
