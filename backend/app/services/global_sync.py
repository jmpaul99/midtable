"""Platform-admin sync of global teams + FIFA ranking catalogs."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Team
from app.providers.base import FootballProvider
from app.providers.fifa_rankings import FifaRankingsError, ParseFifaRankingsProvider
from app.providers.football_data import FootballDataError, respect_rate_limit
from app.services.competitions import AVAILABLE_COMPETITIONS, should_apply_team_kind
from app.services.ranking_catalog import sync_fifa_catalogs

logger = logging.getLogger(__name__)

PROVIDER_KEY = "football-data.org"
_COMPETITION_RATE_LIMIT_ATTEMPTS = 5

T = TypeVar("T")


def default_football_season_year(today: date | None = None) -> int:
    """Season start year (Jul+ → current calendar year, else previous)."""
    d = today or date.today()
    return d.year if d.month >= 7 else d.year - 1


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:  # noqa: BLE001 - best-effort recovery
        logger.exception("global_sync rollback failed")


def _with_rate_limit_retries(
    db: Session,
    label: str,
    op: Callable[[], T],
    *,
    max_attempts: int = _COMPETITION_RATE_LIMIT_ATTEMPTS,
) -> T:
    """Run ``op``, waiting out football-data.org 429s using response headers."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return op()
        except FootballDataError as exc:
            if not exc.rate_limited or attempt >= max_attempts:
                raise
            _rollback_quietly(db)
            logger.warning(
                "global_sync rate limited label=%s attempt=%s/%s; waiting then retrying",
                label,
                attempt,
                max_attempts,
            )
            respect_rate_limit(exc.rate_limit, hit_limit=True)


def upsert_teams_for_competitions(
    db: Session,
    provider: FootballProvider,
    *,
    season_year: int,
) -> dict[str, Any]:
    """Upsert global Team rows for every curated free-plan competition."""
    created = 0
    updated = 0
    competitions: list[dict[str, Any]] = []

    for entry in AVAILABLE_COMPETITIONS:
        code = entry["code"]
        kind = entry["team_kind"]
        summary: dict[str, Any] = {
            "code": code,
            "label": entry["label"],
            "team_kind": kind,
            "requested_season_year": season_year,
            "season_year": season_year,
            "ok": False,
        }
        try:

            def _sync_one() -> dict[str, Any]:
                info, rate = provider.resolve_competition_season_or_latest(
                    code, season_year
                )
                respect_rate_limit(rate)
                if not info.available:
                    return {
                        "skipped": True,
                        "message": info.message or "season not available",
                        "season_year": season_year,
                    }

                used_year = info.season_year
                result: dict[str, Any] = {"season_year": used_year}
                if used_year != season_year:
                    result["fell_back_to_latest"] = True
                    result["message"] = info.message

                teams, rate = provider.list_teams(code, used_year)
                respect_rate_limit(rate)

                external_ids = [pt.external_id for pt in teams]
                existing_by_ext: dict[str, Team] = {}
                if external_ids:
                    existing_by_ext = {
                        t.external_id: t
                        for t in db.scalars(
                            select(Team).where(
                                Team.provider == PROVIDER_KEY,
                                Team.external_id.in_(external_ids),
                            )
                        ).all()
                    }

                created_here = 0
                updated_here = 0
                for pt in teams:
                    team = existing_by_ext.get(pt.external_id)
                    if team is None:
                        db.add(
                            Team(
                                provider=PROVIDER_KEY,
                                external_id=pt.external_id,
                                name=pt.name,
                                short_name=pt.short_name,
                                tla=pt.tla,
                                crest_url=pt.crest_url,
                                team_kind=kind,
                            )
                        )
                        created_here += 1
                        continue
                    changed = False
                    if team.name != pt.name:
                        team.name = pt.name
                        changed = True
                    if team.short_name != pt.short_name:
                        team.short_name = pt.short_name
                        changed = True
                    if team.tla != pt.tla:
                        team.tla = pt.tla
                        changed = True
                    if team.crest_url != pt.crest_url:
                        team.crest_url = pt.crest_url
                        changed = True
                    if should_apply_team_kind(team.team_kind, kind):
                        team.team_kind = kind
                        changed = True
                    if changed:
                        updated_here += 1

                # Commit per competition so rate-limit waits don't hold a long txn,
                # and one failure doesn't poison the rest of the sync.
                db.commit()
                result.update(
                    {
                        "ok": True,
                        "provider_team_count": len(teams),
                        "created": created_here,
                        "updated": updated_here,
                        "external_ids": external_ids,
                    }
                )
                return result

            outcome = _with_rate_limit_retries(db, f"teams:{code}", _sync_one)
            if outcome.get("skipped"):
                summary.update(outcome)
                competitions.append(summary)
                logger.info(
                    "global_sync teams skip code=%s season_year=%s message=%s",
                    code,
                    season_year,
                    summary.get("message"),
                )
                continue

            created += int(outcome.get("created") or 0)
            updated += int(outcome.get("updated") or 0)
            summary.update(outcome)
            logger.info(
                "global_sync teams ok code=%s season_year=%s requested=%s "
                "teams=%s created=%s updated=%s fallback=%s",
                code,
                summary.get("season_year"),
                season_year,
                summary.get("provider_team_count"),
                summary.get("created"),
                summary.get("updated"),
                bool(summary.get("fell_back_to_latest")),
            )
        except FootballDataError as exc:
            _rollback_quietly(db)
            summary["error"] = str(exc)
            if exc.rate_limited:
                # Exhausted retries; still pause so the next competition starts fresh.
                respect_rate_limit(exc.rate_limit, hit_limit=True)
                logger.warning(
                    "global_sync teams rate limited exhausted code=%s", code
                )
            else:
                logger.warning(
                    "global_sync teams failed code=%s error=%s", code, exc
                )
        except Exception as exc:  # noqa: BLE001 - continue other competitions
            _rollback_quietly(db)
            summary["error"] = str(exc)
            logger.exception("global_sync teams unexpected code=%s", code)

        competitions.append(summary)

    ok_count = sum(1 for c in competitions if c.get("ok"))
    return {
        "ok": ok_count > 0,
        "season_year": season_year,
        "created": created,
        "updated": updated,
        "competitions_ok": ok_count,
        "competitions_total": len(competitions),
        "competitions": competitions,
    }


def sync_all_teams_and_rankings(
    db: Session,
    football_provider: FootballProvider,
    *,
    settings: Settings,
    season_year: int | None = None,
) -> dict[str, Any]:
    year = season_year or default_football_season_year()
    logger.info("global_sync started season_year=%s", year)
    teams_summary = upsert_teams_for_competitions(
        db, football_provider, season_year=year
    )

    rankings_summary: dict[str, Any]
    if not settings.parse_api_key.strip():
        rankings_summary = {
            "ok": False,
            "skipped": True,
            "message": "PARSE_API_KEY is not configured",
        }
    else:
        try:
            with ParseFifaRankingsProvider(
                settings.parse_api_key,
                base_url=settings.parse_fifa_base_url,
            ) as fifa_provider:
                rankings_summary = sync_fifa_catalogs(db, fifa_provider)
        except (FifaRankingsError, ValueError) as exc:
            _rollback_quietly(db)
            logger.exception("global_sync rankings failed")
            rankings_summary = {"ok": False, "error": str(exc)}

    snapshots_summary = ensure_table_baselines_for_competitions(
        db,
        football_provider,
        competitions=list(teams_summary.get("competitions") or []),
    )

    # Don't leak large external_id lists in the admin API response.
    for row in teams_summary.get("competitions") or []:
        row.pop("external_ids", None)

    payload = {
        "ok": bool(teams_summary.get("ok"))
        and bool(rankings_summary.get("ok") or rankings_summary.get("skipped")),
        "season_year": year,
        "teams": teams_summary,
        "rankings": rankings_summary,
        "table_snapshots": snapshots_summary,
    }
    logger.info(
        "global_sync finished ok=%s teams_created=%s teams_updated=%s rankings_ok=%s "
        "snapshots_previous=%s snapshots_zeroed=%s",
        payload["ok"],
        teams_summary.get("created"),
        teams_summary.get("updated"),
        rankings_summary.get("ok"),
        snapshots_summary.get("created_previous_final"),
        snapshots_summary.get("created_zeroed_opener"),
    )
    return payload


def ensure_table_baselines_for_competitions(
    db: Session,
    provider: FootballProvider,
    *,
    competitions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create previous-final + zeroed table snapshots when missing (idempotent)."""
    from app.services.standings import ensure_competition_season_table_baselines

    created_previous = 0
    created_zeroed = 0
    ok = 0
    failed = 0
    details: list[dict[str, Any]] = []

    for row in competitions:
        if not row.get("ok"):
            continue
        code = str(row.get("code") or "").upper()
        used_year = int(row.get("season_year") or 0)
        if not code or used_year < 1990:
            continue
        external_ids = [
            str(x) for x in (row.get("external_ids") or []) if x is not None
        ]
        try:

            def _ensure_one() -> dict[str, bool]:
                outcome = ensure_competition_season_table_baselines(
                    db,
                    provider,
                    provider_key=PROVIDER_KEY,
                    competition_code=code,
                    season_year=used_year,
                    fallback_external_ids=external_ids or None,
                )
                db.commit()
                return outcome

            outcome = _with_rate_limit_retries(
                db, f"snapshots:{code}/{used_year}", _ensure_one
            )
            ok += 1
            if outcome.get("created_previous_final"):
                created_previous += 1
            if outcome.get("created_zeroed_opener"):
                created_zeroed += 1
            details.append(
                {
                    "code": code,
                    "season_year": used_year,
                    "ok": True,
                    **outcome,
                }
            )
        except FootballDataError as exc:
            _rollback_quietly(db)
            failed += 1
            details.append(
                {
                    "code": code,
                    "season_year": used_year,
                    "ok": False,
                    "error": str(exc),
                }
            )
            if exc.rate_limited:
                respect_rate_limit(exc.rate_limit, hit_limit=True)
                logger.warning(
                    "global_sync snapshots rate limited exhausted code=%s", code
                )
            else:
                logger.warning(
                    "global_sync snapshots failed code=%s error=%s", code, exc
                )
        except Exception as exc:  # noqa: BLE001
            _rollback_quietly(db)
            failed += 1
            details.append(
                {
                    "code": code,
                    "season_year": used_year,
                    "ok": False,
                    "error": str(exc),
                }
            )
            logger.exception("global_sync snapshots unexpected code=%s", code)

    return {
        "ok": failed == 0,
        "competitions_ok": ok,
        "competitions_failed": failed,
        "created_previous_final": created_previous,
        "created_zeroed_opener": created_zeroed,
        "competitions": details,
    }
