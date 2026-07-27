"""Leaderboard phase presentation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PhaseMatchFilterFields:
    matchweek_range: list[int] | None
    stage_in: list[str] | None


def phase_match_filter_fields(match_filter: dict[str, Any] | None) -> PhaseMatchFilterFields:
    """Parse matchweek_range / stage_in from a phase match_filter dict."""
    mf = match_filter or {}
    matchweek_range: list[int] | None = None
    raw_range = mf.get("matchweek_range")
    if raw_range:
        matchweek_range = [int(x) for x in raw_range]
    elif mf.get("type") == "matchweek_range":
        fr, to = mf.get("from"), mf.get("to")
        if fr is not None and to is not None:
            matchweek_range = [int(fr), int(to)]

    stage_in: list[str] | None = None
    if mf.get("type") == "stage_in":
        stages = mf.get("stages") or []
        stage_in = [str(s) for s in stages]
    else:
        raw_stages = mf.get("stage_in") or mf.get("stages")
        if raw_stages:
            stage_in = [str(s) for s in raw_stages]

    return PhaseMatchFilterFields(matchweek_range=matchweek_range, stage_in=stage_in)
