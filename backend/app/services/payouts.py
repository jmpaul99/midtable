"""Even-split payouts for tied leaderboard ranks (OG competition ranking)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any


def _normalize_phase_key(phase_key: str | None) -> str:
    if not phase_key or phase_key in {"season", "total", "season_total"}:
        return "season"
    return phase_key


def amounts_by_position(
    payouts: Sequence[Mapping[str, Any]] | None,
    phase_key: str | None,
) -> dict[int, Decimal]:
    """Map finishing position (1-based) → prize amount for the given phase."""
    target = _normalize_phase_key(phase_key)
    by_pos: dict[int, Decimal] = {}
    for row in payouts or []:
        phase = _normalize_phase_key(str(row.get("phase") or "season"))
        if phase != target:
            continue
        try:
            position = int(row["position"])
        except (KeyError, TypeError, ValueError):
            continue
        amount = Decimal(str(row.get("amount", 0)))
        by_pos[position] = by_pos.get(position, Decimal(0)) + amount
    return by_pos


def apply_payouts(
    ranked_entries: Sequence[Mapping[str, Any]],
    payouts: Sequence[Mapping[str, Any]] | None,
    phase_key: str | None = None,
) -> list[dict[str, Any]]:
    """Attach even-split `payout` to each entry.

    Tied members at rank ``r`` with group size ``k`` share the sum of prizes for
    positions ``r .. r+k-1`` equally (competition ranking / olympic system).
    """
    prize_by_pos = amounts_by_position(payouts, phase_key)
    out = [dict(e) for e in ranked_entries]
    if not out:
        return out

    i = 0
    n = len(out)
    while i < n:
        rank = int(out[i]["rank"])
        j = i + 1
        while j < n and int(out[j]["rank"]) == rank:
            j += 1
        k = j - i
        pot = sum(
            (prize_by_pos.get(rank + offset, Decimal(0)) for offset in range(k)),
            Decimal(0),
        )
        share = pot / k if k else Decimal(0)
        for idx in range(i, j):
            out[idx]["payout"] = float(share)
        i = j
    return out
