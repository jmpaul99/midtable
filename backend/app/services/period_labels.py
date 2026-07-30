"""Matchweek vs round labels and hybrid stage/matchday period catalogs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

PeriodKind = Literal["matchweek", "round"]

_KNOWN_COMPETITION_TYPES = frozenset({"LEAGUE", "LEAGUE_CUP", "CUP", "PLAYOFFS"})

# Mirror frontend/src/lib/matchStages.ts order (knockout-first then groups/season).
_STAGE_ORDER: tuple[str, ...] = (
    "FINAL",
    "THIRD_PLACE",
    "SEMI_FINALS",
    "QUARTER_FINALS",
    "LAST_16",
    "LAST_32",
    "LAST_64",
    "ROUND_4",
    "ROUND_3",
    "ROUND_2",
    "ROUND_1",
    "GROUP_STAGE",
    "PRELIMINARY_ROUND",
    "QUALIFICATION",
    "QUALIFICATION_ROUND_1",
    "QUALIFICATION_ROUND_2",
    "QUALIFICATION_ROUND_3",
    "PLAYOFF_ROUND_1",
    "PLAYOFF_ROUND_2",
    "PLAYOFFS",
    "REGULAR_SEASON",
    "CHAMPIONSHIP_ROUND",
    "RELEGATION_ROUND",
    "CLAUSURA",
    "APERTURA",
    "CHAMPIONSHIP",
    "RELEGATION",
)

_STAGE_LABELS: dict[str, str] = {
    "FINAL": "Final",
    "THIRD_PLACE": "Third place",
    "SEMI_FINALS": "Semi-finals",
    "QUARTER_FINALS": "Quarter-finals",
    "LAST_16": "Round of 16",
    "LAST_32": "Round of 32",
    "LAST_64": "Round of 64",
    "ROUND_4": "Round 4",
    "ROUND_3": "Round 3",
    "ROUND_2": "Round 2",
    "ROUND_1": "Round 1",
    "GROUP_STAGE": "Group stage",
    "PRELIMINARY_ROUND": "Preliminary round",
    "QUALIFICATION": "Qualification",
    "QUALIFICATION_ROUND_1": "Qualification round 1",
    "QUALIFICATION_ROUND_2": "Qualification round 2",
    "QUALIFICATION_ROUND_3": "Qualification round 3",
    "PLAYOFF_ROUND_1": "Playoff round 1",
    "PLAYOFF_ROUND_2": "Playoff round 2",
    "PLAYOFFS": "Playoffs",
    "REGULAR_SEASON": "Regular season",
    "CHAMPIONSHIP_ROUND": "Championship round",
    "RELEGATION_ROUND": "Relegation round",
    "CLAUSURA": "Clausura",
    "APERTURA": "Apertura",
    "CHAMPIONSHIP": "Championship",
    "RELEGATION": "Relegation",
}

_STAGE_INDEX = {code: i for i, code in enumerate(_STAGE_ORDER)}


@dataclass(frozen=True)
class PeriodDef:
    key: str
    stage: str | None
    scheduled_matchweek: int | None
    label: str


def normalize_competition_type(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = str(value).strip().upper()
    if not trimmed:
        return None
    return trimmed if trimmed in _KNOWN_COMPETITION_TYPES else trimmed


def period_kind(competition_type: str | None) -> PeriodKind:
    return "matchweek" if competition_type == "LEAGUE" else "round"


def format_period_short(n: int, competition_type: str | None) -> str:
    return f"MW{n}" if period_kind(competition_type) == "matchweek" else f"R{n}"


def format_period_long(n: int, competition_type: str | None) -> str:
    word = "Matchweek" if period_kind(competition_type) == "matchweek" else "Round"
    return f"{word} {n}"


def format_period_range(from_n: int, to_n: int, competition_type: str | None) -> str:
    word = "Matchweeks" if period_kind(competition_type) == "matchweek" else "Rounds"
    return f"{word} {from_n}–{to_n}"


def format_period_noun(
    competition_type: str | None,
    *,
    plural: bool = False,
    capitalize: bool = True,
) -> str:
    if period_kind(competition_type) == "matchweek":
        word = "Matchweeks" if plural else "Matchweek"
    else:
        word = "Rounds" if plural else "Round"
    return word if capitalize else word.lower()


def match_stage_label(code: str | None) -> str:
    if not code:
        return "Unknown"
    known = _STAGE_LABELS.get(code)
    if known:
        return known
    return " ".join(part.capitalize() for part in code.split("_") if part)


def scoring_competition_type(pools: Sequence[Any]) -> str | None:
    """Primary scoring pool's competition_type (sort_order, then id)."""
    scoring = [p for p in pools if getattr(p, "scores_match_results", True)]
    if not scoring:
        scoring = list(pools)
    if not scoring:
        return None

    def sort_key(p: Any) -> tuple[int, int]:
        return (int(getattr(p, "sort_order", 0) or 0), int(getattr(p, "id", 0) or 0))

    for pool in sorted(scoring, key=sort_key):
        ctype = getattr(pool, "competition_type", None)
        if ctype:
            return str(ctype)
    return None


def _stage_sort_key(stage: str) -> tuple[int, str]:
    return (_STAGE_INDEX.get(stage, 999), stage)


def build_period_catalog(
    items: Sequence[tuple[str | None, int | None]],
    *,
    competition_type: str | None,
) -> list[PeriodDef]:
    """Build expand/collapse periods from (stage, matchweek) pairs.

    Stages with more than one distinct matchday expand to stage+matchday periods.
    Stages with zero or one distinct matchday collapse to a single stage period.
    """
    by_stage: dict[str, set[int]] = {}
    for raw_stage, mw in items:
        stage = (raw_stage or "").strip()
        by_stage.setdefault(stage, set())
        if mw is not None:
            by_stage[stage].add(int(mw))

    if not by_stage:
        return []

    omit_stage_prefix = competition_type == "LEAGUE" or (
        len(by_stage) == 1 and next(iter(by_stage.keys())) in {"", "REGULAR_SEASON"}
    )

    periods: list[PeriodDef] = []
    for stage in sorted(by_stage.keys(), key=_stage_sort_key):
        matchdays = by_stage[stage]
        stage_or_none = stage or None
        if len(matchdays) > 1:
            for mw in sorted(matchdays):
                short = format_period_short(mw, competition_type)
                if omit_stage_prefix or not stage:
                    label = short
                else:
                    label = f"{match_stage_label(stage)} · {short}"
                periods.append(
                    PeriodDef(
                        key=f"{stage}:{mw}",
                        stage=stage_or_none,
                        scheduled_matchweek=mw,
                        label=label,
                    )
                )
        else:
            if stage:
                label = match_stage_label(stage)
                # LEAGUE regular season with a single matchweek still show MW/R.
                if omit_stage_prefix and matchdays:
                    label = format_period_short(next(iter(matchdays)), competition_type)
                periods.append(
                    PeriodDef(
                        key=stage,
                        stage=stage_or_none,
                        scheduled_matchweek=next(iter(matchdays)) if matchdays else None,
                        label=label,
                    )
                )
            elif matchdays:
                mw = next(iter(matchdays))
                periods.append(
                    PeriodDef(
                        key=f":{mw}",
                        stage=None,
                        scheduled_matchweek=mw,
                        label=format_period_short(mw, competition_type),
                    )
                )
    return periods


def expanded_stages(catalog: Sequence[PeriodDef]) -> frozenset[str]:
    """Stage codes that appear as stage:matchday keys in the catalog."""
    out: set[str] = set()
    for period in catalog:
        if ":" in period.key:
            stage_part = period.key.rsplit(":", 1)[0]
            out.add(stage_part)
    return frozenset(out)


def resolve_period_key(
    stage: str | None,
    matchweek: int | None,
    *,
    expanded: frozenset[str],
) -> str | None:
    stage_key = (stage or "").strip()
    if stage_key in expanded:
        if matchweek is None:
            return None
        return f"{stage_key}:{int(matchweek)}"
    if stage_key:
        return stage_key
    if matchweek is not None and "" in expanded:
        return f":{int(matchweek)}"
    if matchweek is not None and not expanded and not stage_key:
        return f":{int(matchweek)}"
    return None


def catalog_by_key(catalog: Sequence[PeriodDef]) -> dict[str, PeriodDef]:
    return {p.key: p for p in catalog}


def points_by_period_from_events(
    events: Sequence[Any],
    *,
    competition_type: str | None,
) -> list[dict[str, Any]]:
    """Aggregate event points into hybrid periods (ordered)."""
    pairs = [
        (getattr(e, "stage", None), getattr(e, "scheduled_matchweek", None)) for e in events
    ]
    catalog = build_period_catalog(pairs, competition_type=competition_type)
    if not catalog:
        return []
    expanded = expanded_stages(catalog)
    totals: dict[str, float] = {p.key: 0.0 for p in catalog}
    assigned: set[str] = set()
    for event in events:
        key = resolve_period_key(
            getattr(event, "stage", None),
            getattr(event, "scheduled_matchweek", None),
            expanded=expanded,
        )
        if key is None or key not in totals:
            continue
        totals[key] += float(event.points)
        assigned.add(key)
    return [
        {
            "period_key": period.key,
            "label": period.label,
            "stage": period.stage,
            "scheduled_matchweek": period.scheduled_matchweek,
            "points": totals.get(period.key, 0.0),
        }
        for period in catalog
        if period.key in assigned
    ]
