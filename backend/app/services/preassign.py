"""Preassign mode / count helpers."""

from __future__ import annotations

PREASSIGN_MODES = frozenset({"off", "optional", "required"})


def normalize_preassign_mode(value: str | None) -> str:
    raw = (value or "off").lower()
    if raw == "none":
        return "off"
    if raw == "supported":
        return "required"
    if raw in PREASSIGN_MODES:
        return raw
    return "off"


def effective_preassign_count(value: int | None, *, default: int = 1) -> int:
    """Return stored count; only substitute default when value is missing/None.

    Preserves explicit 0 (e.g. optional max 0) unlike ``value or default``.
    """
    return default if value is None else int(value)


def validate_preassign_pair(mode: str | None, count: int | None) -> None:
    """Raise ValueError if required mode is paired with count < 1."""
    normalized = normalize_preassign_mode(mode)
    n = effective_preassign_count(count)
    if normalized == "required" and n < 1:
        raise ValueError("Required preassign mode needs at least 1 team per manager")
