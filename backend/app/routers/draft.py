from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_commissioner, require_league_member
from app.models import DraftState, League, LeagueMember, Team
from app.schemas.draft import DraftPickRequest, DraftStateResponse
from app.services.draft import make_pick, on_clock_member, open_draft, ordered_members

router = APIRouter(tags=["draft"])


@router.get("/leagues/{league_id}/draft", response_model=DraftStateResponse)
def get_draft_state(
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> DraftStateResponse:
    league, _ = membership
    state = db.scalars(select(DraftState).where(DraftState.league_id == league.id)).first()
    if state is None:
        raise HTTPException(status_code=404, detail="Draft state not found")
    on_clock_id = None
    if state.status == "open":
        members = list(
            db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)).all()
        )
        try:
            member, _ = on_clock_member(
                draft_style=league.draft_style,
                ordered=ordered_members(members),
                pick_number=state.current_pick_number,
            )
            on_clock_id = member.public_id
        except HTTPException:
            on_clock_id = None
    return DraftStateResponse(
        id=state.public_id,
        status=state.status,
        current_pick_number=state.current_pick_number,
        on_clock_member_id=on_clock_id,
        league_status=league.status,
    )


@router.post("/leagues/{league_id}/draft/open", response_model=DraftStateResponse)
def open_league_draft(
    membership: tuple[League, LeagueMember] = Depends(require_commissioner),
    db: Session = Depends(get_db),
) -> DraftStateResponse:
    league, member = membership
    open_draft(db, league)
    db.commit()
    return get_draft_state((league, member), db)


@router.post("/leagues/{league_id}/draft/picks")
def submit_pick(
    payload: DraftPickRequest,
    membership: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> dict:
    league, member = membership
    pick = make_pick(
        db,
        league=league,
        picker_member=member,
        team_public_id=payload.team_id,
        allow_commissioner_override=member.is_commissioner,
    )
    db.commit()
    team = db.get(Team, pick.team_id)
    return {
        "id": str(pick.public_id),
        "pick_number": pick.pick_number,
        "round_number": pick.round_number,
        "member_id": str(member.public_id),
        "team_id": str(team.public_id) if team else None,
    }
