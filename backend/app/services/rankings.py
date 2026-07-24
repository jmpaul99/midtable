"""Ranking list paste/upload parse helpers."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class ParsedRankingRow:
    rank: int
    team_name: str


_LINE_RE = re.compile(
    r"^\s*(?:(?P<rank>\d+)\s*[,;\t\-:]?\s*)?(?P<name>.+?)\s*$"
)


def parse_ranking_text(text: str) -> list[ParsedRankingRow]:
    """Parse CSV or pasted 'rank,team' / 'team' lines into ranked rows."""
    stripped = text.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="Ranking text is empty")

    # Prefer CSV when commas/tabs present
    if "," in stripped or "\t" in stripped:
        reader = csv.reader(io.StringIO(stripped))
        rows: list[ParsedRankingRow] = []
        for index, parts in enumerate(reader, start=1):
            parts = [p.strip() for p in parts if p.strip()]
            if not parts:
                continue
            if parts[0].lower() in {"rank", "position", "#"}:
                continue
            if len(parts) >= 2 and parts[0].isdigit():
                rows.append(ParsedRankingRow(rank=int(parts[0]), team_name=parts[1]))
            else:
                rows.append(ParsedRankingRow(rank=index, team_name=parts[0]))
        return _validate(rows)

    rows = []
    for index, line in enumerate(stripped.splitlines(), start=1):
        line = line.strip()
        if not line or line.lower().startswith("rank"):
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue
        rank_raw = match.group("rank")
        name = match.group("name").strip().strip('"').strip("'")
        rank = int(rank_raw) if rank_raw else index
        rows.append(ParsedRankingRow(rank=rank, team_name=name))
    return _validate(rows)


def _validate(rows: list[ParsedRankingRow]) -> list[ParsedRankingRow]:
    if not rows:
        raise HTTPException(status_code=400, detail="No ranking rows parsed")
    ranks = [r.rank for r in rows]
    if len(set(ranks)) != len(ranks):
        raise HTTPException(status_code=400, detail="Duplicate ranks in ranking list")
    return sorted(rows, key=lambda r: r.rank)


def fuzzy_match_score(a: str, b: str) -> float:
    """Simple token overlap score in [0, 1] for name mapping assist."""
    ta = {t for t in re.split(r"\W+", a.lower()) if t}
    tb = {t for t in re.split(r"\W+", b.lower()) if t}
    if not ta or not tb:
        return 0.0
    if a.lower() == b.lower():
        return 1.0
    return len(ta & tb) / len(ta | tb)


def suggest_team_matches(
    parsed: list[ParsedRankingRow],
    teams: list[tuple[str, str]],
) -> list[dict[str, object]]:
    """teams is list of (public_id, name)."""
    suggestions: list[dict[str, object]] = []
    for row in parsed:
        scored = sorted(
            (
                (fuzzy_match_score(row.team_name, name), public_id, name)
                for public_id, name in teams
            ),
            reverse=True,
        )
        best = scored[0] if scored else None
        suggestions.append(
            {
                "rank": row.rank,
                "input_name": row.team_name,
                "suggested_team_id": best[1] if best and best[0] >= 0.34 else None,
                "suggested_team_name": best[2] if best and best[0] >= 0.34 else None,
                "score": best[0] if best else 0.0,
            }
        )
    return suggestions
