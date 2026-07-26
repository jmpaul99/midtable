"""Global ranking catalogs, FIFA sync, and league materialization."""

from __future__ import annotations

import logging
import re
import secrets
from datetime import date

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import (
    League,
    PoolTeam,
    RankingCatalog,
    RankingCatalogEntry,
    RankingCatalogTeamOverride,
    RankingList,
    Team,
    TeamPool,
    TeamRanking,
)
from app.providers.fifa_rankings import FifaRankingRow, ParseFifaRankingsProvider
from app.services.rankings import fuzzy_match_score, parse_ranking_text

logger = logging.getLogger(__name__)

SYSTEM_FIFA_KEYS = ("fifa_men", "fifa_women")
PROVIDER_KEY = "football-data.org"

# FIFA system catalogs only apply to national teams of the matching gender.
CATALOG_TEAM_KIND: dict[str, str] = {
    "fifa_men": "national_men",
    "fifa_women": "national_women",
}


def slugify_catalog_key(label: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_") or "custom"
    return f"{base}_{secrets.token_hex(3)}"


def get_visible_catalogs(db: Session, *, profile_id: int) -> list[RankingCatalog]:
    return list(
        db.scalars(
            select(RankingCatalog)
            .where(
                or_(
                    RankingCatalog.kind == "system",
                    RankingCatalog.owner_profile_id == profile_id,
                )
            )
            .order_by(RankingCatalog.kind.desc(), RankingCatalog.label)
        ).all()
    )


def get_catalog_for_viewer(
    db: Session, *, catalog_id: object, profile_id: int
) -> RankingCatalog | None:
    catalog = db.scalars(
        select(RankingCatalog).where(RankingCatalog.public_id == catalog_id)
    ).first()
    if catalog is None:
        return None
    if catalog.kind == "system":
        return catalog
    if catalog.owner_profile_id == profile_id:
        return catalog
    return None


def create_user_catalog(
    db: Session,
    *,
    profile_id: int,
    label: str,
    text: str,
) -> RankingCatalog:
    parsed = parse_ranking_text(text)
    catalog = RankingCatalog(
        key=slugify_catalog_key(label),
        label=label.strip(),
        kind="user",
        owner_profile_id=profile_id,
        source="manual",
        as_of=date.today(),
    )
    db.add(catalog)
    db.flush()
    for row in parsed:
        db.add(
            RankingCatalogEntry(
                catalog_id=catalog.id,
                rank=row.rank,
                team_name=row.team_name,
            )
        )
    db.commit()
    db.refresh(catalog)
    return catalog


def replace_catalog_entries(
    db: Session,
    catalog: RankingCatalog,
    rows: list[FifaRankingRow],
) -> None:
    db.execute(
        delete(RankingCatalogEntry).where(RankingCatalogEntry.catalog_id == catalog.id)
    )
    as_of: date | None = None
    for row in rows:
        if as_of is None and row.as_of is not None:
            as_of = row.as_of
        db.add(
            RankingCatalogEntry(
                catalog_id=catalog.id,
                rank=row.rank,
                team_name=row.team_name,
                country_code=row.country_code,
                confederation=row.confederation,
            )
        )
    catalog.as_of = as_of or date.today()
    catalog.source = "parse_fifa"


def sync_fifa_catalogs(db: Session, provider: ParseFifaRankingsProvider) -> dict:
    men = provider.fetch_mens()
    women = provider.fetch_womens()
    results: dict[str, dict] = {}
    for key, rows in (("fifa_men", men), ("fifa_women", women)):
        catalog = db.scalars(
            select(RankingCatalog).where(RankingCatalog.key == key)
        ).first()
        if catalog is None:
            catalog = RankingCatalog(
                key=key,
                label=(
                    "FIFA Men's World Ranking"
                    if key == "fifa_men"
                    else "FIFA Women's World Ranking"
                ),
                kind="system",
                source="parse_fifa",
            )
            db.add(catalog)
            db.flush()
        replace_catalog_entries(db, catalog, rows)
        rematerialized = rematerialize_catalog_to_leagues(db, catalog)
        results[key] = {
            "entries": len(rows),
            "as_of": catalog.as_of.isoformat() if catalog.as_of else None,
            "leagues_updated": rematerialized,
        }
        logger.info(
            "fifa catalog synced key=%s entries=%s leagues_updated=%s",
            key,
            len(rows),
            rematerialized,
        )
    db.commit()
    return {"ok": True, "catalogs": results}


def league_pool_teams(db: Session, league: League) -> list[Team]:
    return list(
        db.scalars(
            select(Team)
            .join(PoolTeam, PoolTeam.team_id == Team.id)
            .join(TeamPool, TeamPool.id == PoolTeam.pool_id)
            .where(TeamPool.league_id == league.id)
        ).all()
    )


def team_kind_for_catalog(catalog: RankingCatalog) -> str | None:
    return CATALOG_TEAM_KIND.get(catalog.key)


def candidate_teams_for_catalog(
    db: Session,
    catalog: RankingCatalog,
    *,
    sample_league: League | None = None,
) -> list[Team]:
    """National teams in scope for FIFA matching; empty for non-FIFA / club-only."""
    kind = team_kind_for_catalog(catalog)
    if kind is None:
        # Custom catalogs: keep prior behavior (all pool / all provider teams).
        if sample_league is not None:
            return league_pool_teams(db, sample_league)
        return list(db.scalars(select(Team).where(Team.provider == PROVIDER_KEY)).all())

    if sample_league is not None:
        return [t for t in league_pool_teams(db, sample_league) if t.team_kind == kind]

    return list(
        db.scalars(
            select(Team).where(
                Team.provider == PROVIDER_KEY,
                Team.team_kind == kind,
            )
        ).all()
    )


def _override_map(
    overrides: list[RankingCatalogTeamOverride],
) -> tuple[dict[str, str], dict[str, str]]:
    by_code: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for o in overrides:
        if o.country_code:
            by_code[o.country_code.strip().upper()] = o.external_team_id
        if o.team_name:
            by_name[o.team_name.strip().lower()] = o.external_team_id
    return by_code, by_name


def match_team_for_entry(
    entry: RankingCatalogEntry,
    teams: list[Team],
    *,
    overrides_by_code: dict[str, str],
    overrides_by_name: dict[str, str],
) -> Team | None:
    if entry.country_code:
        ext = overrides_by_code.get(entry.country_code.strip().upper())
        if ext:
            hit = next(
                (
                    t
                    for t in teams
                    if t.provider == PROVIDER_KEY and t.external_id == ext
                ),
                None,
            )
            if hit:
                return hit
    ext = overrides_by_name.get(entry.team_name.strip().lower())
    if ext:
        hit = next(
            (t for t in teams if t.provider == PROVIDER_KEY and t.external_id == ext),
            None,
        )
        if hit:
            return hit

    if entry.country_code:
        code = entry.country_code.strip().upper()
        for team in teams:
            tla = (team.tla or "").strip().upper()
            if tla and tla == code:
                return team

    name_l = entry.team_name.strip().lower()
    for team in teams:
        if team.name.strip().lower() == name_l:
            return team
        if team.short_name and team.short_name.strip().lower() == name_l:
            return team

    best: tuple[float, Team] | None = None
    for team in teams:
        score = max(
            fuzzy_match_score(entry.team_name, team.name),
            fuzzy_match_score(entry.team_name, team.short_name or ""),
        )
        if best is None or score > best[0]:
            best = (score, team)
    if best and best[0] >= 0.34:
        return best[1]
    return None


def ensure_league_ranking_list(
    db: Session, league: League, catalog: RankingCatalog
) -> RankingList:
    row = db.scalars(
        select(RankingList).where(
            RankingList.league_id == league.id,
            RankingList.key == catalog.key,
        )
    ).first()
    if row is None:
        row = RankingList(
            league_id=league.id,
            key=catalog.key,
            label=catalog.label,
            source=catalog.source,
            as_of=catalog.as_of,
            locked=False,
        )
        db.add(row)
        db.flush()
    else:
        if not row.locked:
            row.label = catalog.label
            row.source = catalog.source
            row.as_of = catalog.as_of
    return row


def materialize_catalog_into_league(
    db: Session, league: League, catalog: RankingCatalog
) -> dict:
    ranking_list = ensure_league_ranking_list(db, league, catalog)
    if ranking_list.locked:
        return {
            "league_id": str(league.public_id),
            "skipped": "locked",
            "matched": 0,
            "unmatched": 0,
        }

    entries = list(
        db.scalars(
            select(RankingCatalogEntry)
            .where(RankingCatalogEntry.catalog_id == catalog.id)
            .order_by(RankingCatalogEntry.rank)
        ).all()
    )
    overrides = list(
        db.scalars(
            select(RankingCatalogTeamOverride).where(
                RankingCatalogTeamOverride.catalog_id == catalog.id
            )
        ).all()
    )
    by_code, by_name = _override_map(overrides)
    teams = candidate_teams_for_catalog(db, catalog, sample_league=league)

    for existing in db.scalars(
        select(TeamRanking).where(TeamRanking.ranking_list_id == ranking_list.id)
    ).all():
        db.delete(existing)
    db.flush()

    matched = 0
    seen_teams: set[int] = set()
    for entry in entries:
        team = match_team_for_entry(
            entry,
            teams,
            overrides_by_code=by_code,
            overrides_by_name=by_name,
        )
        if team is None or team.id in seen_teams:
            continue
        seen_teams.add(team.id)
        db.add(
            TeamRanking(
                ranking_list_id=ranking_list.id,
                team_id=team.id,
                rank=entry.rank,
            )
        )
        matched += 1
    # Unmatched = national competition teams in the league without a FIFA rank.
    unmatched = sum(1 for t in teams if t.id not in seen_teams)
    return {
        "league_id": str(league.public_id),
        "matched": matched,
        "unmatched": unmatched,
    }


def rematerialize_catalog_to_leagues(db: Session, catalog: RankingCatalog) -> int:
    leagues_by_id: dict[int, League] = {}
    for league in db.scalars(select(League)).all():
        rules = league.upset_rules or {}
        if (
            rules.get("rank_source") == "fixed_ranking_at_event_start"
            and rules.get("ranking_list_key") == catalog.key
        ):
            leagues_by_id[league.id] = league
    for ranking_list in db.scalars(
        select(RankingList).where(
            RankingList.key == catalog.key,
            RankingList.locked.is_(False),
        )
    ).all():
        if ranking_list.league_id not in leagues_by_id:
            league = db.get(League, ranking_list.league_id)
            if league is not None:
                leagues_by_id[league.id] = league

    updated = 0
    for league in leagues_by_id.values():
        result = materialize_catalog_into_league(db, league, catalog)
        if result.get("skipped") != "locked":
            updated += 1
    return updated


def upsert_override(
    db: Session,
    catalog: RankingCatalog,
    *,
    country_code: str | None,
    team_name: str | None,
    provider: str,
    external_team_id: str,
) -> RankingCatalogTeamOverride:
    if not country_code and not team_name:
        raise ValueError("country_code or team_name is required")
    q = select(RankingCatalogTeamOverride).where(
        RankingCatalogTeamOverride.catalog_id == catalog.id
    )
    if country_code:
        row = db.scalars(
            q.where(
                RankingCatalogTeamOverride.country_code.ilike(country_code.strip())
            )
        ).first()
    else:
        row = db.scalars(
            q.where(RankingCatalogTeamOverride.team_name.ilike(team_name.strip()))
        ).first()
    if row is None:
        row = RankingCatalogTeamOverride(catalog_id=catalog.id)
        db.add(row)
    row.country_code = country_code.strip().upper() if country_code else None
    row.team_name = team_name.strip() if team_name else None
    row.provider = provider
    row.external_team_id = external_team_id
    db.flush()
    rematerialize_catalog_to_leagues(db, catalog)
    db.commit()
    db.refresh(row)
    return row


def _entry_has_override(
    entry: RankingCatalogEntry,
    *,
    overrides_by_code: dict[str, str],
    overrides_by_name: dict[str, str],
) -> bool:
    if entry.country_code and entry.country_code.strip().upper() in overrides_by_code:
        return True
    if entry.team_name.strip().lower() in overrides_by_name:
        return True
    return False


def _best_suggestion(
    entry: RankingCatalogEntry, teams: list[Team]
) -> tuple[Team | None, float]:
    scored = sorted(
        (
            (
                max(
                    fuzzy_match_score(entry.team_name, t.name),
                    fuzzy_match_score(entry.team_name, t.short_name or ""),
                    1.0
                    if entry.country_code
                    and (t.tla or "").upper() == entry.country_code.upper()
                    else 0.0,
                ),
                t,
            )
            for t in teams
        ),
        key=lambda x: x[0],
        reverse=True,
    )
    best = scored[0] if scored else None
    if best and best[0] >= 0.34:
        return best[1], best[0]
    return None, best[0] if best else 0.0


def _best_entry_suggestion(
    team: Team, entries: list[RankingCatalogEntry]
) -> tuple[RankingCatalogEntry | None, float]:
    scored = sorted(
        (
            (
                max(
                    fuzzy_match_score(entry.team_name, team.name),
                    fuzzy_match_score(entry.team_name, team.short_name or ""),
                    1.0
                    if entry.country_code
                    and (team.tla or "").upper() == entry.country_code.upper()
                    else 0.0,
                ),
                entry,
            )
            for entry in entries
        ),
        key=lambda x: x[0],
        reverse=True,
    )
    best = scored[0] if scored else None
    if best and best[0] >= 0.34:
        return best[1], best[0]
    return None, best[0] if best else 0.0


def matches_for_catalog(
    db: Session, catalog: RankingCatalog, *, sample_league: League | None = None
) -> list[dict]:
    """Resolve every catalog entry to a national team (or none), for admin review."""
    entries = list(
        db.scalars(
            select(RankingCatalogEntry)
            .where(RankingCatalogEntry.catalog_id == catalog.id)
            .order_by(RankingCatalogEntry.rank)
        ).all()
    )
    overrides = list(
        db.scalars(
            select(RankingCatalogTeamOverride).where(
                RankingCatalogTeamOverride.catalog_id == catalog.id
            )
        ).all()
    )
    by_code, by_name = _override_map(overrides)
    teams = candidate_teams_for_catalog(db, catalog, sample_league=sample_league)

    out: list[dict] = []
    for entry in entries:
        team = match_team_for_entry(
            entry,
            teams,
            overrides_by_code=by_code,
            overrides_by_name=by_name,
        )
        suggestion, score = (None, 0.0)
        if team is None:
            suggestion, score = _best_suggestion(entry, teams)
        source = None
        if team is not None:
            source = (
                "override"
                if _entry_has_override(
                    entry, overrides_by_code=by_code, overrides_by_name=by_name
                )
                else "auto"
            )
        out.append(
            {
                "rank": entry.rank,
                "team_name": entry.team_name,
                "country_code": entry.country_code,
                "matched_external_team_id": team.external_id if team else None,
                "matched_team_name": team.name if team else None,
                "match_source": source,
                "suggested_external_team_id": (
                    suggestion.external_id if suggestion else None
                ),
                "suggested_team_name": suggestion.name if suggestion else None,
                "score": score if team is None else 1.0,
            }
        )
    return out


def unmatched_for_catalog(
    db: Session, catalog: RankingCatalog, *, sample_league: League | None = None
) -> list[dict]:
    """National competition teams in scope with no FIFA catalog match."""
    entries = list(
        db.scalars(
            select(RankingCatalogEntry)
            .where(RankingCatalogEntry.catalog_id == catalog.id)
            .order_by(RankingCatalogEntry.rank)
        ).all()
    )
    overrides = list(
        db.scalars(
            select(RankingCatalogTeamOverride).where(
                RankingCatalogTeamOverride.catalog_id == catalog.id
            )
        ).all()
    )
    by_code, by_name = _override_map(overrides)
    teams = candidate_teams_for_catalog(db, catalog, sample_league=sample_league)

    matched_ids: set[int] = set()
    for entry in entries:
        team = match_team_for_entry(
            entry,
            teams,
            overrides_by_code=by_code,
            overrides_by_name=by_name,
        )
        if team is not None:
            matched_ids.add(team.id)

    out: list[dict] = []
    for team in sorted(teams, key=lambda t: t.name.lower()):
        if team.id in matched_ids:
            continue
        suggestion, score = _best_entry_suggestion(team, entries)
        out.append(
            {
                "external_team_id": team.external_id,
                "team_name": team.name,
                "tla": team.tla,
                "suggested_rank": suggestion.rank if suggestion else None,
                "suggested_team_name": suggestion.team_name if suggestion else None,
                "suggested_country_code": (
                    suggestion.country_code if suggestion else None
                ),
                "score": score,
            }
        )
    return out


def league_ranking_status(db: Session, league: League) -> list[dict]:
    key = (league.upset_rules or {}).get("ranking_list_key")
    catalogs_by_key = {
        c.key: c
        for c in db.scalars(select(RankingCatalog)).all()
    }
    rows = db.scalars(
        select(RankingList).where(RankingList.league_id == league.id)
    ).all()
    status: list[dict] = []
    for row in rows:
        catalog = catalogs_by_key.get(row.key)
        entry_count = len(
            db.scalars(
                select(TeamRanking).where(TeamRanking.ranking_list_id == row.id)
            ).all()
        )
        unmatched = 0
        if catalog is not None and not row.locked:
            unmatched = len(unmatched_for_catalog(db, catalog, sample_league=league))
        status.append(
            {
                "id": row.public_id,
                "key": row.key,
                "label": row.label,
                "source": row.source,
                "as_of": row.as_of,
                "locked": row.locked,
                "entry_count": entry_count,
                "unmatched_count": unmatched,
                "is_selected": bool(key and key == row.key),
            }
        )
    if key and not any(s["key"] == key for s in status):
        catalog = catalogs_by_key.get(key)
        if catalog is not None:
            status.append(
                {
                    "id": catalog.public_id,
                    "key": catalog.key,
                    "label": catalog.label,
                    "source": catalog.source,
                    "as_of": catalog.as_of,
                    "locked": False,
                    "entry_count": 0,
                    "unmatched_count": 0,
                    "is_selected": True,
                }
            )
    return status


def ensure_fixed_ranking_for_league(db: Session, league: League) -> None:
    """Materialize catalog ranks when league uses fixed ranking source."""
    rules = league.upset_rules or {}
    if rules.get("rank_source") != "fixed_ranking_at_event_start":
        return
    key = rules.get("ranking_list_key")
    if not key:
        return
    catalog = db.scalars(
        select(RankingCatalog).where(RankingCatalog.key == key)
    ).first()
    if catalog is None:
        return
    materialize_catalog_into_league(db, league, catalog)
