import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_profile
from app.db import get_db
from app.deps import get_league_by_public_id, require_platform_admin
from app.models import (
    Profile,
    RankingCatalog,
    RankingCatalogEntry,
    RankingCatalogTeamOverride,
    Team,
)
from app.schemas.ranking_catalog import (
    RankingCatalogCreate,
    RankingCatalogDetailResponse,
    RankingCatalogEntryResponse,
    RankingCatalogOverrideResponse,
    RankingCatalogOverrideUpsert,
    RankingCatalogResponse,
    RankingCatalogUnmatchedRow,
)
from app.services.ranking_catalog import (
    create_user_catalog,
    get_catalog_for_viewer,
    get_visible_catalogs,
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
    stmt = select(Team).where(Team.provider == "football-data.org").order_by(Team.name)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Team.name.ilike(like),
                Team.short_name.ilike(like),
                Team.tla.ilike(like),
            )
        )
    teams = db.scalars(stmt.limit(200)).all()
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
