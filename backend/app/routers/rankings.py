import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_commissioner, require_league_member
from app.logging_config import log_id
from app.models import League, LeagueMember, PoolTeam, RankingList, Team, TeamPool, TeamRanking
from app.schemas.rankings import RankingImportRequest, RankingListCreate, RankingListResponse
from app.services.rankings import parse_ranking_text, suggest_team_matches

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rankings"])


@router.get("/leagues/{league_id}/ranking-lists", response_model=list[RankingListResponse])
def list_ranking_lists(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> list[RankingListResponse]:
    league, _ = membership
    rows = db.scalars(select(RankingList).where(RankingList.league_id == league.id)).all()
    return [RankingListResponse.model_validate(row) for row in rows]


@router.post(
    "/leagues/{league_id}/ranking-lists",
    response_model=RankingListResponse,
    status_code=201,
)
def create_ranking_list(
    payload: RankingListCreate,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> RankingListResponse:
    league, _ = membership
    row = RankingList(
        league_id=league.id,
        key=payload.key,
        label=payload.label,
        source=payload.source,
        as_of=payload.as_of,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "ranking list created league_id=%s list_id=%s key=%s",
        league.public_id,
        row.public_id,
        row.key,
    )
    return RankingListResponse.model_validate(row)


@router.post("/leagues/{league_id}/ranking-lists/{list_id}/parse")
def parse_rankings(
    list_id: UUID,
    payload: RankingImportRequest,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    ranking_list = db.scalars(
        select(RankingList).where(
            RankingList.public_id == list_id,
            RankingList.league_id == league.id,
        )
    ).first()
    if ranking_list is None:
        raise HTTPException(status_code=404, detail="Ranking list not found")
    if ranking_list.locked:
        raise HTTPException(status_code=409, detail="Ranking list is locked")

    parsed = parse_ranking_text(payload.text)
    teams = db.scalars(
        select(Team)
        .join(PoolTeam, PoolTeam.team_id == Team.id)
        .join(TeamPool, TeamPool.id == PoolTeam.pool_id)
        .where(TeamPool.league_id == league.id)
    ).all()
    team_pairs = [(str(t.public_id), t.name) for t in teams]
    suggestions = suggest_team_matches(parsed, team_pairs)
    logger.info(
        "ranking parse league_id=%s list_id=%s parsed_rows=%s",
        log_id(league),
        ranking_list.public_id,
        len(parsed),
    )
    return {"rows": suggestions}


@router.post("/leagues/{league_id}/ranking-lists/{list_id}/entries", status_code=201)
def import_ranking_entries(
    list_id: UUID,
    payload: RankingImportRequest,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    ranking_list = db.scalars(
        select(RankingList).where(
            RankingList.public_id == list_id,
            RankingList.league_id == league.id,
        )
    ).first()
    if ranking_list is None:
        raise HTTPException(status_code=404, detail="Ranking list not found")
    if ranking_list.locked:
        raise HTTPException(status_code=409, detail="Ranking list is locked")

    parsed = parse_ranking_text(payload.text)
    mappings = payload.mappings or {}
    teams = {
        t.public_id: t
        for t in db.scalars(
            select(Team)
            .join(PoolTeam, PoolTeam.team_id == Team.id)
            .join(TeamPool, TeamPool.id == PoolTeam.pool_id)
            .where(TeamPool.league_id == league.id)
        ).all()
    }

    # Clear existing entries then insert
    for existing in db.scalars(
        select(TeamRanking).where(TeamRanking.ranking_list_id == ranking_list.id)
    ).all():
        db.delete(existing)

    created = 0
    for row in parsed:
        team_id = mappings.get(row.rank)
        if team_id is None:
            # try exact name match
            team = next((t for t in teams.values() if t.name.lower() == row.team_name.lower()), None)
        else:
            team = teams.get(team_id)
        if team is None:
            raise HTTPException(
                status_code=400,
                detail=f"Could not map rank {row.rank} ({row.team_name}) to a team",
            )
        db.add(
            TeamRanking(
                ranking_list_id=ranking_list.id,
                team_id=team.id,
                rank=row.rank,
            )
        )
        created += 1
    db.commit()
    logger.info(
        "ranking entries imported league_id=%s list_id=%s created=%s",
        league.public_id,
        ranking_list.public_id,
        created,
    )
    return {"created": created}


@router.post("/leagues/{league_id}/ranking-lists/{list_id}/lock")
def lock_ranking_list(
    list_id: UUID,
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> dict:
    league, _ = membership
    ranking_list = db.scalars(
        select(RankingList).where(
            RankingList.public_id == list_id,
            RankingList.league_id == league.id,
        )
    ).first()
    if ranking_list is None:
        raise HTTPException(status_code=404, detail="Ranking list not found")
    ranking_list.locked = True
    db.commit()
    logger.info(
        "ranking list locked league_id=%s list_id=%s key=%s",
        league.public_id,
        ranking_list.public_id,
        ranking_list.key,
    )
    return {"id": str(ranking_list.public_id), "locked": True}
