"""Tests for commissioner complete / delete league endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers import leagues_core


def test_complete_league_sets_status(monkeypatch):
    league = SimpleNamespace(id=1, public_id=uuid4(), status="active")
    member = SimpleNamespace(id=2, public_id=uuid4())
    db = MagicMock()
    detail = SimpleNamespace(status="complete")
    monkeypatch.setattr(leagues_core, "_league_detail", lambda *_a, **_k: detail)

    result = leagues_core.complete_league(membership=(league, member), db=db)

    assert league.status == "complete"
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(league)
    assert result is detail


def test_complete_league_rejects_already_complete():
    league = SimpleNamespace(id=1, status="complete")
    member = SimpleNamespace(id=2)
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        leagues_core.complete_league(membership=(league, member), db=db)

    assert exc.value.status_code == 409
    db.commit.assert_not_called()


def test_delete_league_removes_row():
    league = SimpleNamespace(id=1, status="active")
    member = SimpleNamespace(id=2)
    db = MagicMock()

    result = leagues_core.delete_league(membership=(league, member), db=db)

    assert result.status_code == 204
    db.delete.assert_called_once_with(league)
    db.commit.assert_called_once()
