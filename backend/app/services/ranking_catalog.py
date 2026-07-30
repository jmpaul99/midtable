"""Global ranking catalogs, FIFA sync, and league materialization."""

from __future__ import annotations

import logging
import re
import secrets
from datetime import date

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from decimal import Decimal

from app.models import (
    League,
    PoolTeam,
    RankingCatalog,
    RankingCatalogEntry,
    RankingCatalogTeamOverride,
    RankingFreeze,
    RankingFreezeEntry,
    RankingList,
    Team,
    TeamPool,
    TeamRanking,
)
from app.providers.fifa_rankings import FifaRankingRow, ParseFifaRankingsProvider
from app.services.rankings import fuzzy_match_score, parse_ranking_text
from app.services.scoring import RankedTeam, UpsetRules

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
        # Unlocked leagues read catalogs live; no per-league rematerialize.
        results[key] = {
            "entries": len(rows),
            "as_of": catalog.as_of.isoformat() if catalog.as_of else None,
            "leagues_updated": 0,
        }
        logger.info(
            "fifa catalog synced key=%s entries=%s",
            key,
            len(rows),
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


def resolve_catalog_team_ranks(
    db: Session,
    catalog: RankingCatalog,
    *,
    sample_league: League | None = None,
) -> dict[int, int]:
    """Map team_id -> rank from live catalog entries + overrides."""
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
    # Index once — match_team_for_entry used to linear-scan (+ fuzzy) per entry.
    by_external_id = {
        t.external_id: t
        for t in teams
        if t.provider == PROVIDER_KEY and t.external_id
    }
    by_tla: dict[str, Team] = {}
    by_team_name: dict[str, Team] = {}
    for t in teams:
        tla = (t.tla or "").strip().upper()
        if tla and tla not in by_tla:
            by_tla[tla] = t
        name_l = t.name.strip().lower()
        if name_l and name_l not in by_team_name:
            by_team_name[name_l] = t
        if t.short_name:
            short_l = t.short_name.strip().lower()
            if short_l and short_l not in by_team_name:
                by_team_name[short_l] = t

    ranks: dict[int, int] = {}
    unmatched: list[RankingCatalogEntry] = []
    for entry in entries:
        team: Team | None = None
        if entry.country_code:
            ext = by_code.get(entry.country_code.strip().upper())
            if ext:
                team = by_external_id.get(ext)
        if team is None:
            ext = by_name.get(entry.team_name.strip().lower())
            if ext:
                team = by_external_id.get(ext)
        if team is None and entry.country_code:
            team = by_tla.get(entry.country_code.strip().upper())
        if team is None:
            team = by_team_name.get(entry.team_name.strip().lower())
        if team is None or team.id in ranks:
            if team is None:
                unmatched.append(entry)
            continue
        ranks[team.id] = entry.rank

    # Fuzzy only for leftovers — avoids O(entries × teams) on the common path.
    claimed = set(ranks.keys())
    remaining_teams = [t for t in teams if t.id not in claimed]
    for entry in unmatched:
        team = match_team_for_entry(
            entry,
            remaining_teams,
            overrides_by_code=by_code,
            overrides_by_name=by_name,
        )
        if team is None or team.id in ranks:
            continue
        ranks[team.id] = entry.rank
        remaining_teams = [t for t in remaining_teams if t.id != team.id]
    return ranks


def ensure_or_create_ranking_freeze(
    db: Session,
    catalog: RankingCatalog,
    *,
    as_of: date | None = None,
    sample_league: League | None = None,
) -> RankingFreeze:
    """Create or reuse a shared freeze for catalog at as_of."""
    freeze_as_of = as_of or catalog.as_of or date.today()
    existing = db.scalars(
        select(RankingFreeze).where(
            RankingFreeze.catalog_id == catalog.id,
            RankingFreeze.as_of == freeze_as_of,
        )
    ).first()
    if existing is not None:
        return existing

    freeze = RankingFreeze(catalog_id=catalog.id, as_of=freeze_as_of)
    db.add(freeze)
    db.flush()
    ranks = resolve_catalog_team_ranks(db, catalog, sample_league=sample_league)
    for team_id, rank in ranks.items():
        db.add(
            RankingFreezeEntry(
                freeze_id=freeze.id,
                team_id=team_id,
                rank=rank,
            )
        )
    db.flush()
    logger.info(
        "ranking freeze created catalog=%s as_of=%s teams=%s",
        catalog.key,
        freeze_as_of.isoformat(),
        len(ranks),
    )
    return freeze


def materialize_catalog_into_league(
    db: Session, league: League, catalog: RankingCatalog
) -> dict:
    """Ensure league ranking_list metadata exists; unlocked catalogs stay live."""
    ranking_list = ensure_league_ranking_list(db, league, catalog)
    if ranking_list.locked:
        entry_count = 0
        if ranking_list.freeze_id:
            entry_count = len(
                db.scalars(
                    select(RankingFreezeEntry).where(
                        RankingFreezeEntry.freeze_id == ranking_list.freeze_id
                    )
                ).all()
            )
        return {
            "league_id": str(league.public_id),
            "skipped": "locked",
            "matched": entry_count,
            "unmatched": 0,
        }

    # Drop any stale unlocked team_rankings copies for catalog-backed lists.
    for existing in db.scalars(
        select(TeamRanking).where(TeamRanking.ranking_list_id == ranking_list.id)
    ).all():
        db.delete(existing)
    db.flush()

    ranks = resolve_catalog_team_ranks(db, catalog, sample_league=league)
    teams = candidate_teams_for_catalog(db, catalog, sample_league=league)
    unmatched = sum(1 for t in teams if t.id not in ranks)
    return {
        "league_id": str(league.public_id),
        "matched": len(ranks),
        "unmatched": unmatched,
    }


def rematerialize_catalog_to_leagues(db: Session, catalog: RankingCatalog) -> int:
    """Refresh unlocked league list metadata for a catalog (no rank copies)."""
    updated = 0
    for league in db.scalars(select(League)).all():
        rules = league.upset_rules or {}
        uses_catalog = (
            rules.get("rank_source") == "fixed_ranking_at_event_start"
            and rules.get("ranking_list_key") == catalog.key
        )
        ranking_list = db.scalars(
            select(RankingList).where(
                RankingList.league_id == league.id,
                RankingList.key == catalog.key,
            )
        ).first()
        if not uses_catalog and ranking_list is None:
            continue
        if ranking_list is not None and ranking_list.locked:
            continue
        materialize_catalog_into_league(db, league, catalog)
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
    # Live catalog reads pick up overrides immediately; refresh list metadata only.
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
        if row.locked and row.freeze_id:
            entry_count = len(
                db.scalars(
                    select(RankingFreezeEntry).where(
                        RankingFreezeEntry.freeze_id == row.freeze_id
                    )
                ).all()
            )
        elif row.source == "manual" or catalog is None:
            entry_count = len(
                db.scalars(
                    select(TeamRanking).where(TeamRanking.ranking_list_id == row.id)
                ).all()
            )
        else:
            entry_count = len(
                resolve_catalog_team_ranks(db, catalog, sample_league=league)
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
            ranks = resolve_catalog_team_ranks(db, catalog, sample_league=league)
            unmatched = len(unmatched_for_catalog(db, catalog, sample_league=league))
            status.append(
                {
                    "id": catalog.public_id,
                    "key": catalog.key,
                    "label": catalog.label,
                    "source": catalog.source,
                    "as_of": catalog.as_of,
                    "locked": False,
                    "entry_count": len(ranks),
                    "unmatched_count": unmatched,
                    "is_selected": True,
                }
            )
    return status


def ranks_for_league(
    db: Session,
    league: League,
    upset_rules: UpsetRules,
) -> dict[int, RankedTeam] | None:
    """Resolve fixed ranks from stored freeze / TeamRanking rows only.

    Admin catalog matching + overrides are applied when a freeze is created
    (draft open / ranking lock). Draft polls must not re-run live fuzzy match.
    """
    if upset_rules.rank_source != "fixed_ranking_at_event_start":
        return None
    key = upset_rules.ranking_list_key
    if not key:
        return None

    ranking_list = db.scalars(
        select(RankingList).where(
            RankingList.league_id == league.id,
            RankingList.key == key,
        )
    ).first()
    catalog = db.scalars(
        select(RankingCatalog).where(RankingCatalog.key == key)
    ).first()

    team_ranks: dict[int, int] = {}
    freeze_id = ranking_list.freeze_id if ranking_list is not None else None

    if freeze_id is None and catalog is not None and catalog.as_of is not None:
        shared = db.scalars(
            select(RankingFreeze).where(
                RankingFreeze.catalog_id == catalog.id,
                RankingFreeze.as_of == catalog.as_of,
            )
        ).first()
        if shared is not None:
            freeze_id = shared.id

    if freeze_id is not None:
        for row in db.scalars(
            select(RankingFreezeEntry).where(
                RankingFreezeEntry.freeze_id == freeze_id
            )
        ).all():
            team_ranks[row.team_id] = row.rank
    elif ranking_list is not None:
        for row in db.scalars(
            select(TeamRanking).where(TeamRanking.ranking_list_id == ranking_list.id)
        ).all():
            team_ranks[row.team_id] = row.rank
    else:
        return None

    if not team_ranks:
        return None

    played = max(upset_rules.min_played, 0)
    return {
        team_id: RankedTeam(
            team_id=team_id,
            rank=rank,
            played=played,
            points=Decimal(0),
            goals_for=0,
            goals_against=0,
            goal_difference=0,
        )
        for team_id, rank in team_ranks.items()
    }


def freeze_catalog_for_league_lock(db: Session, league: League, key: str) -> int:
    """Lock league ranking list and attach shared catalog freeze."""
    catalog = db.scalars(
        select(RankingCatalog).where(RankingCatalog.key == key)
    ).first()
    ranking_list = db.scalars(
        select(RankingList).where(
            RankingList.league_id == league.id,
            RankingList.key == key,
        )
    ).first()

    if ranking_list is not None and ranking_list.locked:
        return 0

    if catalog is not None:
        if ranking_list is None:
            ranking_list = ensure_league_ranking_list(db, league, catalog)
        freeze = ensure_or_create_ranking_freeze(
            db, catalog, as_of=catalog.as_of, sample_league=league
        )
        ranking_list.freeze_id = freeze.id
        ranking_list.as_of = freeze.as_of
        ranking_list.locked = True
        # Catalog-backed lists should not keep unlocked team_rankings copies.
        for existing in db.scalars(
            select(TeamRanking).where(TeamRanking.ranking_list_id == ranking_list.id)
        ).all():
            db.delete(existing)
        db.flush()
        logger.info(
            "auto-locked ranking via freeze league_id=%s key=%s freeze_id=%s",
            league.public_id,
            key,
            freeze.id,
        )
        return 1

    if ranking_list is None:
        return 0
    ranking_list.locked = True
    db.flush()
    logger.info(
        "auto-locked manual ranking list league_id=%s key=%s",
        league.public_id,
        key,
    )
    return 1


def ensure_fixed_ranking_for_league(db: Session, league: League) -> None:
    """Ensure catalog-backed ranking list metadata exists for fixed-rank leagues."""
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
