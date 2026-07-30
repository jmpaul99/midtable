"""Competition domestic tier resolution and admin updates."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.competitions import (
    curated_domestic_tier,
    domestic_tier_for_competition,
    ensure_competition_tiers,
    list_competition_tiers_for_admin,
    resolve_domestic_tiers,
    update_competition_tiers,
)


def test_curated_domestic_tiers():
    assert curated_domestic_tier("PL") == 1
    assert curated_domestic_tier("ELC") == 2
    assert curated_domestic_tier("CL") is None
    assert domestic_tier_for_competition("pd") == 1


def test_ensure_competition_tiers_seeds_missing(monkeypatch):
    db = MagicMock()
    existing = SimpleNamespace(
        competition_code="PL",
        domestic_tier=1,
        updated_at=datetime.now(UTC),
    )
    db.scalars.return_value.all.return_value = [existing]

    added: list[object] = []
    db.add.side_effect = added.append

    rows = ensure_competition_tiers(db)
    assert any(getattr(r, "competition_code", None) == "PL" for r in rows)
    # Should seed other curated codes beyond PL
    assert len(added) >= 10
    db.flush.assert_called()


def test_resolve_domestic_tiers_prefers_db_override(monkeypatch):
    db = MagicMock()

    def fake_ensure(session):
        return []

    monkeypatch.setattr(
        "app.services.competitions.ensure_competition_tiers",
        fake_ensure,
    )
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(competition_code="PL", domestic_tier=1),
        SimpleNamespace(competition_code="ELC", domestic_tier=3),  # overridden
        SimpleNamespace(competition_code="CL", domestic_tier=None),
    ]
    tiers = resolve_domestic_tiers(db)
    assert tiers["PL"] == 1
    assert tiers["ELC"] == 3
    assert tiers["CL"] is None
    assert tiers["PD"] == 1  # curated fallback fill


def test_update_competition_tiers(monkeypatch):
    db = MagicMock()
    pl = SimpleNamespace(competition_code="PL", domestic_tier=1, updated_at=None)
    elc = SimpleNamespace(competition_code="ELC", domestic_tier=2, updated_at=None)

    def fake_ensure(session):
        return [pl, elc]

    monkeypatch.setattr(
        "app.services.competitions.ensure_competition_tiers",
        fake_ensure,
    )
    db.scalars.return_value.all.return_value = [pl, elc]

    listed = [
        {
            "code": "PL",
            "label": "Premier League",
            "key": "premier_league",
            "team_kind": "club",
            "domestic_tier": 1,
            "default_domestic_tier": 1,
        },
        {
            "code": "ELC",
            "label": "Championship",
            "key": "championship",
            "team_kind": "club",
            "domestic_tier": 3,
            "default_domestic_tier": 2,
        },
    ]
    monkeypatch.setattr(
        "app.services.competitions.list_competition_tiers_for_admin",
        lambda session: listed,
    )

    out = update_competition_tiers(db, [("ELC", 3)])
    assert elc.domestic_tier == 3
    assert elc.updated_at is not None
    assert out == listed
    db.flush.assert_called()


def test_update_competition_tiers_rejects_unknown_code(monkeypatch):
    db = MagicMock()
    pl = SimpleNamespace(competition_code="PL", domestic_tier=1, updated_at=None)
    monkeypatch.setattr(
        "app.services.competitions.ensure_competition_tiers",
        lambda session: [pl],
    )
    db.scalars.return_value.all.return_value = [pl]
    try:
        update_competition_tiers(db, [("ELC", 3), ("unknown", 9)])
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "unknown" in str(exc).lower()
    assert pl.domestic_tier == 1


def test_update_competition_tiers_rejects_zero(monkeypatch):
    db = MagicMock()
    pl = SimpleNamespace(competition_code="PL", domestic_tier=1, updated_at=None)
    monkeypatch.setattr(
        "app.services.competitions.ensure_competition_tiers",
        lambda session: [pl],
    )
    db.scalars.return_value.all.return_value = [pl]
    try:
        update_competition_tiers(db, [("PL", 0)])
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "domestic_tier" in str(exc)


def test_list_competition_tiers_for_admin_shape(monkeypatch):
    monkeypatch.setattr(
        "app.services.competitions.resolve_domestic_tiers",
        lambda db: {"PL": 1, "ELC": 2, "CL": None, "PD": 1, "BL1": 1, "DED": 1,
                    "BSA": 1, "FL1": 1, "PPL": 1, "SA": 1, "WC": None, "EC": None},
    )
    rows = list_competition_tiers_for_admin(MagicMock())
    codes = {r["code"] for r in rows}
    assert "PL" in codes and "ELC" in codes and "CL" in codes
    # Numbered tiers before cups
    first_cup = next(i for i, r in enumerate(rows) if r["domestic_tier"] is None)
    assert all(rows[i]["domestic_tier"] is not None for i in range(first_cup))
