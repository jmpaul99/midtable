"""Platform-admin sync of global teams + FIFA ranking catalogs."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Team
from app.providers.base import FootballProvider, RateLimitInfo
from app.providers.fifa_rankings import FifaRankingsError, ParseFifaRankingsProvider
from app.providers.football_data import FootballDataError
from app.services.competitions import AVAILABLE_COMPETITIONS, should_apply_team_kind
from app.services.ranking_catalog import sync_fifa_catalogs

logger = logging.getLogger(__name__)

PROVIDER_KEY = "football-data.org"


def default_football_season_year(today: date | None = None) -> int:
    """Season start year (Jul+ → current calendar year, else previous)."""
    d = today or date.today()
    return d.year if d.month >= 7 else d.year - 1


def _respect_rate_limit(rate: RateLimitInfo) -> None:
    if rate.requests_available_minute is not None and rate.requests_available_minute <= 2:
        wait = rate.retry_after_seconds or 8
        logger.info("global_sync waiting for rate budget wait_s=%s", wait)
        time.sleep(wait)


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:  # noqa: BLE001 - best-effort recovery
        logger.exception("global_sync rollback failed")


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
            info, rate = provider.resolve_competition_season_or_latest(
                code, season_year
            )
            _respect_rate_limit(rate)
            if not info.available:
                summary["skipped"] = True
                summary["message"] = info.message or "season not available"
                competitions.append(summary)
                logger.info(
                    "global_sync teams skip code=%s season_year=%s message=%s",
                    code,
                    season_year,
                    summary["message"],
                )
                continue

            used_year = info.season_year
            summary["season_year"] = used_year
            if used_year != season_year:
                summary["fell_back_to_latest"] = True
                summary["message"] = info.message

            teams, rate = provider.list_teams(code, used_year)
            _respect_rate_limit(rate)

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
            created += created_here
            updated += updated_here
            summary.update(
                {
                    "ok": True,
                    "provider_team_count": len(teams),
                    "created": created_here,
                    "updated": updated_here,
                }
            )
            logger.info(
                "global_sync teams ok code=%s season_year=%s requested=%s "
                "teams=%s created=%s updated=%s fallback=%s",
                code,
                used_year,
                season_year,
                len(teams),
                created_here,
                updated_here,
                used_year != season_year,
            )
        except FootballDataError as exc:
            _rollback_quietly(db)
            summary["error"] = str(exc)
            if exc.rate_limited:
                wait = exc.rate_limit.retry_after_seconds or 60
                logger.warning(
                    "global_sync teams rate limited code=%s wait_s=%s", code, wait
                )
                time.sleep(wait)
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

    payload = {
        "ok": bool(teams_summary.get("ok"))
        and bool(rankings_summary.get("ok") or rankings_summary.get("skipped")),
        "season_year": year,
        "teams": teams_summary,
        "rankings": rankings_summary,
    }
    logger.info(
        "global_sync finished ok=%s teams_created=%s teams_updated=%s rankings_ok=%s",
        payload["ok"],
        teams_summary.get("created"),
        teams_summary.get("updated"),
        rankings_summary.get("ok"),
    )
    return payload
