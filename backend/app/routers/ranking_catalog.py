import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.config import Settings, get_settings
from app.db import get_db
from app.deps import (
    get_football_provider,
    get_league_by_public_id,
    require_platform_admin,
)
from app.models import (
    Profile,
    RankingCatalog,
    RankingCatalogEntry,
    RankingCatalogTeamOverride,
    Team,
)
from app.providers.football_data import FootballDataError, FootballDataProvider
from app.schemas.ranking_catalog import (
    AdminSyncTeamsAndRankingsRequest,
    CompetitionTeamResponse,
    CompetitionTeamsRequest,
    CompetitionTeamsResponse,
    RankingCatalogCreate,
    RankingCatalogDetailResponse,
    RankingCatalogEntryResponse,
    RankingCatalogMatchRow,
    RankingCatalogOverrideResponse,
    RankingCatalogOverrideUpsert,
    RankingCatalogResponse,
    RankingCatalogUnmatchedRow,
)
from app.services.competitions import (
    is_allowed_competition_code,
    normalize_competition_code,
)
from app.services.global_sync import sync_all_teams_and_rankings
from app.services.ranking_catalog import (
    create_user_catalog,
    get_catalog_for_viewer,
    get_visible_catalogs,
    matches_for_catalog,
    unmatched_for_catalog,
    upsert_override,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ranking-catalog"])


@router.get("/ranking-catalogs", response_model=list[RankingCatalogResponse])
def list_ranking_catalogs(
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> list[RankingCatalogResponse]:
    rows = get_visible_catalogs(db, profile_id=profile.id)
    return [RankingCatalogResponse.model_validate(row) for row in rows]


@router.post("/competitions/teams", response_model=CompetitionTeamsResponse)
def list_competition_teams(
    payload: CompetitionTeamsRequest,
    _profile: Profile = Depends(get_current_profile),
    provider: FootballDataProvider = Depends(get_football_provider),
) -> CompetitionTeamsResponse:
    """Load provider teams for the given competition code/season pairs."""
    if not payload.competitions:
        raise HTTPException(status_code=400, detail="At least one competition is required")

    seen_queries: set[tuple[str, int]] = set()
    by_external_id: dict[str, CompetitionTeamResponse] = {}

    for item in payload.competitions:
        code = normalize_competition_code(item.code)
        if not code or not is_allowed_competition_code(code):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported competition code: {item.code!r}",
            )
        if item.season_year < 1990 or item.season_year > 2100:
            raise HTTPException(status_code=400, detail="Invalid season_year")

        query_key = (code, item.season_year)
        if query_key in seen_queries:
            continue
        seen_queries.add(query_key)

        try:
            info, _ = provider.resolve_competition_season_or_latest(code, item.season_year)
            if not info.available:
                raise HTTPException(
                    status_code=400,
                    detail=info.message or f"Season not available for {code}",
                )
            teams, _ = provider.list_teams(code, info.season_year)
        except FootballDataError as exc:
            logger.warning(
                "competition teams provider error code=%s season=%s err=%s",
                code,
                item.season_year,
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail=f"Failed to load teams for {code}: {exc}",
            ) from exc

        for team in teams:
            if team.external_id in by_external_id:
                continue
            by_external_id[team.external_id] = CompetitionTeamResponse(
                external_id=team.external_id,
                name=team.name,
                short_name=team.short_name,
                crest_url=team.crest_url,
                competition_code=code,
            )

    ordered = sorted(by_external_id.values(), key=lambda t: t.name.casefold())
    return CompetitionTeamsResponse(teams=ordered)


@router.post(
    "/ranking-catalogs",
    response_model=RankingCatalogResponse,
    status_code=201,
)
def create_ranking_catalog(
    payload: RankingCatalogCreate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> RankingCatalogResponse:
    label = payload.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label is required")
    catalog = create_user_catalog(
        db, profile_id=profile.id, label=label, text=payload.text
    )
    logger.info(
        "ranking catalog created id=%s key=%s owner=%s",
        catalog.public_id,
        catalog.key,
        profile.public_id,
    )
    return RankingCatalogResponse.model_validate(catalog)


@router.get(
    "/ranking-catalogs/{catalog_id}",
    response_model=RankingCatalogDetailResponse,
)
def get_ranking_catalog(
    catalog_id: UUID,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> RankingCatalogDetailResponse:
    catalog = get_catalog_for_viewer(db, catalog_id=catalog_id, profile_id=profile.id)
    if catalog is None:
        raise HTTPException(status_code=404, detail="Ranking catalog not found")
    entries = db.scalars(
        select(RankingCatalogEntry)
        .where(RankingCatalogEntry.catalog_id == catalog.id)
        .order_by(RankingCatalogEntry.rank)
    ).all()
    base = RankingCatalogResponse.model_validate(catalog)
    return RankingCatalogDetailResponse(
        **base.model_dump(),
        entries=[RankingCatalogEntryResponse.model_validate(e) for e in entries],
    )


@router.get(
    "/ranking-catalogs/{catalog_id}/unmatched",
    response_model=list[RankingCatalogUnmatchedRow],
)
def list_unmatched_catalog_entries(
    catalog_id: UUID,
    league_id: UUID | None = Query(default=None),
    _admin: Profile = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[RankingCatalogUnmatchedRow]:
    catalog = db.scalars(
        select(RankingCatalog).where(RankingCatalog.public_id == catalog_id)
    ).first()
    if catalog is None:
        raise HTTPException(status_code=404, detail="Ranking catalog not found")
    sample = get_league_by_public_id(db, league_id) if league_id else None
    rows = unmatched_for_catalog(db, catalog, sample_league=sample)
    return [RankingCatalogUnmatchedRow.model_validate(r) for r in rows]


@router.get(
    "/ranking-catalogs/{catalog_id}/matches",
    response_model=list[RankingCatalogMatchRow],
)
def list_catalog_matches(
    catalog_id: UUID,
    league_id: UUID | None = Query(default=None),
    _admin: Profile = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[RankingCatalogMatchRow]:
    catalog = db.scalars(
        select(RankingCatalog).where(RankingCatalog.public_id == catalog_id)
    ).first()
    if catalog is None:
        raise HTTPException(status_code=404, detail="Ranking catalog not found")
    sample = get_league_by_public_id(db, league_id) if league_id else None
    rows = matches_for_catalog(db, catalog, sample_league=sample)
    return [RankingCatalogMatchRow.model_validate(r) for r in rows]


@router.get(
    "/ranking-catalogs/{catalog_id}/overrides",
    response_model=list[RankingCatalogOverrideResponse],
)
def list_catalog_overrides(
    catalog_id: UUID,
    _admin: Profile = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[RankingCatalogOverrideResponse]:
    catalog = db.scalars(
        select(RankingCatalog).where(RankingCatalog.public_id == catalog_id)
    ).first()
    if catalog is None:
        raise HTTPException(status_code=404, detail="Ranking catalog not found")
    rows = db.scalars(
        select(RankingCatalogTeamOverride).where(
            RankingCatalogTeamOverride.catalog_id == catalog.id
        )
    ).all()
    return [RankingCatalogOverrideResponse.model_validate(r) for r in rows]


@router.put(
    "/ranking-catalogs/{catalog_id}/overrides",
    response_model=RankingCatalogOverrideResponse,
)
def put_catalog_override(
    catalog_id: UUID,
    payload: RankingCatalogOverrideUpsert,
    _admin: Profile = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> RankingCatalogOverrideResponse:
    catalog = db.scalars(
        select(RankingCatalog).where(RankingCatalog.public_id == catalog_id)
    ).first()
    if catalog is None:
        raise HTTPException(status_code=404, detail="Ranking catalog not found")
    if not payload.country_code and not payload.team_name:
        raise HTTPException(
            status_code=400, detail="country_code or team_name is required"
        )
    team = db.scalars(
        select(Team).where(
            Team.provider == payload.provider,
            Team.external_id == payload.external_team_id,
        )
    ).first()
    if team is None:
        raise HTTPException(status_code=400, detail="Unknown external team id")
    try:
        row = upsert_override(
            db,
            catalog,
            country_code=payload.country_code,
            team_name=payload.team_name,
            provider=payload.provider,
            external_team_id=payload.external_team_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "ranking catalog override saved catalog_id=%s external_team_id=%s",
        catalog.public_id,
        payload.external_team_id,
    )
    return RankingCatalogOverrideResponse.model_validate(row)


@router.get("/admin/teams")
def list_teams_for_admin_rematch(
    q: str | None = Query(default=None),
    _admin: Profile = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Search football-data.org teams for rematch pickers.

    Without ``q``, returns an empty list so clients use search rather than
    loading an incomplete global dump.
    """
    needle = (q or "").strip()
    if not needle:
        return []
    like = f"%{needle}%"
    teams = db.scalars(
        select(Team)
        .where(
            Team.provider == "football-data.org",
            or_(
                Team.name.ilike(like),
                Team.short_name.ilike(like),
                Team.tla.ilike(like),
            ),
        )
        .order_by(Team.name)
        .limit(100)
    ).all()
    return [
        {
            "external_id": t.external_id,
            "name": t.name,
            "short_name": t.short_name,
            "tla": t.tla,
            "provider": t.provider,
        }
        for t in teams
    ]


@router.post("/admin/sync-teams-and-rankings")
def admin_sync_teams_and_rankings(
    payload: AdminSyncTeamsAndRankingsRequest | None = None,
    _admin: Profile = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    provider: FootballDataProvider = Depends(get_football_provider),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Upsert global teams for all free-plan competitions, then refresh FIFA catalogs."""
    body = payload or AdminSyncTeamsAndRankingsRequest()
    if body.season_year is not None and (
        body.season_year < 1990 or body.season_year > 2100
    ):
        raise HTTPException(status_code=400, detail="Invalid season_year")
    logger.info(
        "admin sync-teams-and-rankings started season_year=%s",
        body.season_year,
    )
    result = sync_all_teams_and_rankings(
        db,
        provider,
        settings=settings,
        season_year=body.season_year,
    )
    if not result.get("ok") and not result.get("teams", {}).get("ok"):
        raise HTTPException(status_code=502, detail=result)
    return result
