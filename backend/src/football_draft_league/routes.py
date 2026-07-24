import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from football_draft_league.auth import CurrentUser
from football_draft_league.config import get_settings
from football_draft_league.db import get_session
from football_draft_league.repository import Repository, row, rows
from football_draft_league.schemas import (
    AuditEntry,
    BonusOut,
    BonusWrite,
    BootstrapRequest,
    DraftOrderWrite,
    DraftPickCreate,
    DraftStart,
    DraftStateOut,
    DuplicateTemplate,
    InviteAccept,
    InviteCreate,
    InviteOut,
    LeagueCreate,
    LeagueDetail,
    LeagueSummary,
    Message,
    PickCorrection,
    PoolTeamOut,
    PreassignmentWrite,
    ProviderParamsWrite,
    RankingImport,
    RankingListCreate,
    RankingListOut,
    ReadinessOut,
    RosterCorrection,
    StandingsOut,
    SyncOut,
    SyncRequest,
    TemplateOut,
    TemplateWrite,
)
from football_draft_league.services import (
    DraftService,
    compute_standings,
    json_value,
    league_phases,
    parse_ranking_rows,
    team_available,
)
from football_draft_league.sync_service import SyncService

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]


def _template_out(item: dict[str, Any]) -> dict[str, Any]:
    scoring = dict(item["scoring_config"])
    return {
        "id": item["public_id"],
        "code": item["code"],
        "name": item["name"],
        "provider": item["provider"],
        "provider_competition_code": item["provider_competition_code"],
        "default_team_count": item["default_team_count"],
        "default_roster_size": item["default_roster_size"],
        "pools": item["pool_definitions"],
        "scoring": {k: v for k, v in scoring.items() if k not in {"phases", "manual_bonus_defaults"}},
        "phases": scoring.get("phases", []),
        "leaderboard_tiebreaks": item["tiebreak_config"],
        "bonuses": scoring.get("manual_bonus_defaults", {}),
        "payouts": item["payout_config"],
        "draft": item["draft_config"],
        "is_active": item["is_active"],
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
    }


def _require_admin(user: CurrentUser) -> None:
    if user.role not in {"service_role", "admin"} and user.claims.get("app_metadata", {}).get(
        "role"
    ) not in {"admin", "service_role"}:
        raise HTTPException(status_code=403, detail="Administrator required")


async def _league_match_id(
    repo: Repository, league_internal_id: int, match_public_id: UUID | None
) -> int | None:
    if match_public_id is None:
        return None
    value = (
        await repo.execute(
            """
            select m.id from matches m
            join leagues l on l.competition_id=m.competition_id
            where l.id=:league and m.public_id=:match
            """,
            {"league": league_internal_id, "match": match_public_id},
        )
    ).scalar_one_or_none()
    if value is None:
        raise HTTPException(status_code=422, detail="Match is not in this league")
    return int(value)


@router.get("/competition-templates", response_model=list[TemplateOut], tags=["templates"])
async def list_templates(session: Session, _: CurrentUser) -> list[dict[str, Any]]:
    repo = Repository(session)
    return [
        _template_out(item)
        for item in rows(
            await repo.execute(
                "select * from competition_templates order by is_active desc, name"
            )
        )
    ]


@router.get("/competition-templates/{template_id}", response_model=TemplateOut, tags=["templates"])
async def get_template(template_id: UUID, session: Session, _: CurrentUser) -> dict[str, Any]:
    item = row(
        await Repository(session).execute(
            "select * from competition_templates where public_id=:id", {"id": template_id}
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Competition template not found")
    return _template_out(item)


@router.post(
    "/competition-templates", response_model=TemplateOut, status_code=201, tags=["templates"]
)
async def create_template(
    payload: TemplateWrite, session: Session, user: CurrentUser
) -> dict[str, Any]:
    _require_admin(user)
    repo = Repository(session)
    scoring = {**payload.scoring, "phases": payload.phases, "manual_bonus_defaults": payload.bonuses}
    item = row(
        await repo.execute(
            """
            insert into competition_templates
              (code,name,provider,provider_competition_code,default_team_count,
               default_roster_size,pool_definitions,scoring_config,tiebreak_config,
               payout_config,draft_config,is_active)
            values (:code,:name,:provider,:provider_code,:team_count,:roster_size,
                    cast(:pools as jsonb),cast(:scoring as jsonb),cast(:tiebreaks as jsonb),
                    cast(:payouts as jsonb),cast(:draft as jsonb),:active)
            returning *
            """,
            {
                "code": payload.code,
                "name": payload.name,
                "provider": payload.provider,
                "provider_code": payload.provider_competition_code,
                "team_count": payload.default_team_count,
                "roster_size": payload.default_roster_size,
                "pools": json_value([item.model_dump(mode="json") for item in payload.pools]),
                "scoring": json_value(scoring),
                "tiebreaks": json_value(payload.leaderboard_tiebreaks),
                "payouts": json_value(payload.payouts),
                "draft": json_value(payload.draft),
                "active": payload.is_active,
            },
        )
    )
    assert item
    return _template_out(item)


@router.put("/competition-templates/{template_id}", response_model=TemplateOut, tags=["templates"])
async def update_template(
    template_id: UUID, payload: TemplateWrite, session: Session, user: CurrentUser
) -> dict[str, Any]:
    _require_admin(user)
    scoring = {**payload.scoring, "phases": payload.phases, "manual_bonus_defaults": payload.bonuses}
    item = row(
        await Repository(session).execute(
            """
            update competition_templates set code=:code,name=:name,provider=:provider,
              provider_competition_code=:provider_code,default_team_count=:team_count,
              default_roster_size=:roster_size,pool_definitions=cast(:pools as jsonb),
              scoring_config=cast(:scoring as jsonb),tiebreak_config=cast(:tiebreaks as jsonb),
              payout_config=cast(:payouts as jsonb),draft_config=cast(:draft as jsonb),
              is_active=:active where public_id=:id returning *
            """,
            {
                "id": template_id,
                "code": payload.code,
                "name": payload.name,
                "provider": payload.provider,
                "provider_code": payload.provider_competition_code,
                "team_count": payload.default_team_count,
                "roster_size": payload.default_roster_size,
                "pools": json_value([item.model_dump(mode="json") for item in payload.pools]),
                "scoring": json_value(scoring),
                "tiebreaks": json_value(payload.leaderboard_tiebreaks),
                "payouts": json_value(payload.payouts),
                "draft": json_value(payload.draft),
                "active": payload.is_active,
            },
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Competition template not found")
    return _template_out(item)


@router.delete(
    "/competition-templates/{template_id}", response_model=Message, tags=["templates"]
)
async def deactivate_template(
    template_id: UUID, session: Session, user: CurrentUser
) -> Message:
    _require_admin(user)
    result = await Repository(session).execute(
        "update competition_templates set is_active=false where public_id=:id",
        {"id": template_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Competition template not found")
    return Message(detail="Template deactivated")


@router.post(
    "/competition-templates/{template_id}/duplicate",
    response_model=TemplateOut,
    status_code=201,
    tags=["templates"],
)
async def duplicate_template(
    template_id: UUID, payload: DuplicateTemplate, session: Session, user: CurrentUser
) -> dict[str, Any]:
    _require_admin(user)
    item = row(
        await Repository(session).execute(
            """
            insert into competition_templates
              (code,name,provider,provider_competition_code,default_team_count,
               default_roster_size,pool_definitions,scoring_config,tiebreak_config,
               payout_config,draft_config,is_active)
            select :code,:name,provider,provider_competition_code,default_team_count,
              default_roster_size,pool_definitions,scoring_config,tiebreak_config,
              payout_config,draft_config,true
            from competition_templates where public_id=:id returning *
            """,
            {"id": template_id, "code": payload.code, "name": payload.name},
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Competition template not found")
    return _template_out(item)


@router.get("/leagues", response_model=list[LeagueSummary], tags=["leagues"])
async def list_leagues(session: Session, user: CurrentUser) -> list[dict[str, Any]]:
    return rows(
        await Repository(session).execute(
            """
            select l.public_id id,l.name,l.slug,l.status,l.visibility,l.max_members,lm.role,
                   c.season,ct.public_id template_id
            from profiles p join league_members lm on lm.profile_id=p.id and lm.status='active'
            join leagues l on l.id=lm.league_id join competitions c on c.id=l.competition_id
            join competition_templates ct on ct.id=c.template_id
            where p.auth_user_id=:auth order by l.created_at desc
            """,
            {"auth": user.id},
        )
    )


@router.post("/leagues", response_model=LeagueDetail, status_code=201, tags=["leagues"])
async def create_league(
    payload: LeagueCreate, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    profile = await repo.profile(user)
    template_id = await repo.template_internal_id(payload.template_id)
    template = row(
        await repo.execute(
            "select * from competition_templates where id=:id and is_active=true",
            {"id": template_id},
        )
    )
    if not template:
        raise HTTPException(status_code=422, detail="Template is inactive")
    competition = row(
        await repo.execute(
            """
            insert into competitions (template_id,season)
            values (:template,:season)
            on conflict (template_id,season) do update set season=excluded.season
            returning id
            """,
            {
                "template": template_id,
                "season": payload.season,
            },
        )
    )
    assert competition
    settings = {**template["draft_config"], **payload.settings}
    league = row(
        await repo.execute(
            """
            insert into leagues
              (competition_id,owner_profile_id,name,slug,visibility,max_members,settings,
               provider_params)
            values (:competition,:owner,:name,:slug,:visibility,:max_members,
                    cast(:settings as jsonb),cast(:provider_params as jsonb))
            returning *
            """,
            {
                "competition": competition["id"],
                "owner": profile["id"],
                "name": payload.name,
                "slug": payload.slug,
                "visibility": payload.visibility,
                "max_members": payload.max_members,
                "settings": json_value(settings),
                "provider_params": json_value(payload.provider_params),
            },
        )
    )
    assert league
    member = row(
        await repo.execute(
            """
            insert into league_members (league_id,profile_id,role)
            values (:league,:profile,'owner') returning id,public_id,role
            """,
            {"league": league["id"], "profile": profile["id"]},
        )
    )
    assert member
    for ordinal, pool_config in enumerate(template["pool_definitions"], 1):
        pool = row(
            await repo.execute(
                """
                insert into pools
                  (league_id,definition_key,name,ordinal,roster_size,
                   provider_competition_code,scoring_enabled)
                values (:league,:key,:name,:ordinal,:size,:code,:scoring) returning id
                """,
                {
                    "league": league["id"],
                    "key": pool_config["key"],
                    "name": pool_config["name"],
                    "ordinal": ordinal,
                    "size": pool_config["slots_per_member"],
                    "code": pool_config["provider_competition_code"],
                    "scoring": pool_config.get("scoring_enabled", True),
                },
            )
        )
        assert pool
        await repo.execute(
            """
            insert into draft_states (pool_id,status,current_pick_number,current_round)
            values (:pool,'pending',1,1)
            """,
            {"pool": pool["id"]},
        )
        for slot_number in range(1, pool_config["slots_per_member"] + 1):
            await repo.execute(
                """
                insert into roster_slots (pool_id,league_member_id,slot_number,label)
                values (:pool,:member,:slot,:label)
                """,
                {
                    "pool": pool["id"],
                    "member": member["id"],
                    "slot": slot_number,
                    "label": pool_config.get("slot_label"),
                },
            )
    return await _league_detail(repo, league["public_id"], user)


async def _league_detail(
    repo: Repository, league_id: UUID, user: CurrentUser
) -> dict[str, Any]:
    access = await repo.league_access(league_id, user)
    detail = row(
        await repo.execute(
            """
            select l.public_id id,l.name,l.slug,l.status,l.visibility,l.max_members,l.settings,
                   c.season,ct.public_id template_id,l.created_at,:role role,l.provider_params,
                   ct.scoring_config
            from leagues l join competitions c on c.id=l.competition_id
            join competition_templates ct on ct.id=c.template_id where l.id=:id
            """,
            {"id": access["league_id"], "role": access["role"]},
        )
    )
    assert detail
    detail["current_member_id"] = access["member_public_id"]
    detail["pools"] = rows(
        await repo.execute(
            """
            select public_id id,definition_key,name,ordinal,roster_size,draft_order,
                   provider_competition_code,scoring_enabled,provider_params
            from pools where league_id=:id order by ordinal
            """,
            {"id": access["league_id"]},
        )
    )
    detail["members"] = rows(
        await repo.execute(
            """
            select lm.public_id id,p.public_id profile_id,p.display_name,lm.role,lm.status,lm.joined_at
            from league_members lm join profiles p on p.id=lm.profile_id
            where lm.league_id=:id order by lm.joined_at
            """,
            {"id": access["league_id"]},
        )
    )
    detail["phases"] = await league_phases(repo, access["league_id"])
    detail["bonus_type_keys"] = list(
        detail.pop("scoring_config").get("manual_bonus_defaults", {})
    )
    if access["role"] not in {"owner", "commissioner"}:
        detail["provider_params"] = {}
        for pool in detail["pools"]:
            pool["provider_params"] = {}
    return detail


@router.get("/leagues/{league_id}", response_model=LeagueDetail, tags=["leagues"])
async def get_league(league_id: UUID, session: Session, user: CurrentUser) -> dict[str, Any]:
    return await _league_detail(Repository(session), league_id, user)


@router.get("/pools/{pool_id}/teams", response_model=list[PoolTeamOut], tags=["pools"])
async def list_pool_teams(
    pool_id: UUID,
    session: Session,
    user: CurrentUser,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    repo = Repository(session)
    pool, _ = await repo.pool(pool_id, user)
    teams = rows(
        await repo.execute(
            """
            select t.public_id id,t.name,t.crest_url,t.provider_team_id,
              exists (
                select 1 from draft_picks dp where dp.pool_team_id=pt.id
              ) drafted,
              case when owner.member_id is null then null else
                jsonb_build_object(
                  'member_id',owner.member_id,
                  'display_name',owner.display_name,
                  'acquired_via',owner.acquired_via
                )
              end current_owner
            from pool_teams pt join teams t on t.id=pt.team_id
            left join lateral (
              select lm.public_id member_id,pr.display_name,re.acquired_via
              from roster_entries re
              join roster_slots rs on rs.id=re.roster_slot_id and rs.pool_id=pt.pool_id
              join league_members lm on lm.id=rs.league_member_id and lm.status='active'
              join profiles pr on pr.id=lm.profile_id
              where re.pool_team_id=pt.id and re.valid_until is null
              order by re.valid_from desc,re.id desc limit 1
            ) owner on true
            where pt.pool_id=:pool
            order by owner.member_id is not null,t.name
            """,
            {"pool": pool["id"]},
        )
    )
    for team in teams:
        team["available"] = team_available(team["current_owner"])
    return [team for team in teams if team["available"] or not available_only]


@router.put("/leagues/{league_id}/provider-params", response_model=LeagueDetail, tags=["seasons"])
async def save_provider_params(
    league_id: UUID,
    payload: ProviderParamsWrite,
    session: Session,
    user: CurrentUser,
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    await repo.execute(
        "update leagues set provider_params=cast(:params as jsonb) where id=:league",
        {"params": json_value(payload.league), "league": access["league_id"]},
    )
    for public_id, params in payload.pools.items():
        result = await repo.execute(
            """
            update pools set provider_params=cast(:params as jsonb)
            where public_id=:pool and league_id=:league
            """,
            {
                "params": json_value(params),
                "pool": public_id,
                "league": access["league_id"],
            },
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=422, detail=f"Unknown pool: {public_id}")
    return await _league_detail(repo, league_id, user)


@router.post("/leagues/{league_id}/invites", response_model=InviteOut, tags=["invites"])
async def create_invite(
    league_id: UUID, payload: InviteCreate, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=payload.expires_in_hours)
    invite = row(
        await repo.execute(
            """
            insert into invites
              (league_id,invited_by_member_id,email,token_hash,role,expires_at)
            values (:league,:member,lower(:email),:hash,:role,:expires)
            returning public_id id,email,role,status,expires_at
            """,
            {
                "league": access["league_id"],
                "member": access["member_id"],
                "email": str(payload.email),
                "hash": hashlib.sha256(token.encode()).hexdigest(),
                "role": "commissioner" if payload.commissioner else "member",
                "expires": expires,
            },
        )
    )
    assert invite
    invite["token"] = token
    return invite


@router.get("/leagues/{league_id}/invites", response_model=list[InviteOut], tags=["invites"])
async def list_invites(
    league_id: UUID, session: Session, user: CurrentUser
) -> list[dict[str, Any]]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    return rows(
        await repo.execute(
            """
            select public_id id,email,role,status,expires_at,null::text token
            from invites where league_id=:league order by created_at desc
            """,
            {"league": access["league_id"]},
        )
    )


@router.delete("/leagues/{league_id}/invites/{invite_id}", response_model=Message, tags=["invites"])
async def revoke_invite(
    league_id: UUID, invite_id: UUID, session: Session, user: CurrentUser
) -> Message:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    result = await repo.execute(
        """
        update invites set status='revoked'
        where public_id=:invite and league_id=:league and status='pending'
        """,
        {"invite": invite_id, "league": access["league_id"]},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Pending invite not found")
    return Message(detail="Invite revoked")


@router.post("/invites/accept", response_model=LeagueSummary, tags=["invites"])
async def accept_invite(
    payload: InviteAccept, session: Session, user: CurrentUser
) -> dict[str, Any]:
    if not user.email:
        raise HTTPException(status_code=403, detail="Verified token email is required")
    metadata = user.claims.get("user_metadata", {})
    if not (
        metadata.get("email_verified") is True
        or user.claims.get("email_confirmed_at")
        or user.claims.get("confirmed_at")
    ):
        raise HTTPException(status_code=403, detail="Email address is not verified")
    repo = Repository(session)
    invite = row(
        await repo.execute(
            """
            select i.*,l.max_members from invites i join leagues l on l.id=i.league_id
            where i.token_hash=:hash for update
            """,
            {"hash": hashlib.sha256(payload.token.encode()).hexdigest()},
        )
    )
    if not invite or invite["status"] != "pending" or invite["expires_at"] <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Invite is invalid or expired")
    if not invite["email"] or invite["email"].casefold() != user.email.casefold():
        raise HTTPException(status_code=403, detail="Invite email does not match verified email")
    active_count = int(
        (
            await repo.execute(
                "select count(*) from league_members where league_id=:league and status='active'",
                {"league": invite["league_id"]},
            )
        ).scalar_one()
    )
    if active_count >= invite["max_members"]:
        raise HTTPException(status_code=409, detail="League is full")
    profile = await repo.profile(user, payload.display_name)
    member = row(
        await repo.execute(
            """
            insert into league_members (league_id,profile_id,role,status)
            values (:league,:profile,:role,'active')
            on conflict (league_id,profile_id) do update set role=excluded.role,status='active'
            returning id
            """,
            {"league": invite["league_id"], "profile": profile["id"], "role": invite["role"]},
        )
    )
    assert member
    await repo.execute(
        """
        insert into roster_slots (pool_id,league_member_id,slot_number,label)
        select p.id,:member,n,null from pools p
        cross join lateral generate_series(1,p.roster_size) n
        where p.league_id=:league on conflict do nothing
        """,
        {"member": member["id"], "league": invite["league_id"]},
    )
    await repo.execute(
        """
        update invites set status='accepted',accepted_by_profile_id=:profile,accepted_at=now()
        where id=:id
        """,
        {"profile": profile["id"], "id": invite["id"]},
    )
    return row(
        await repo.execute(
            """
            select l.public_id id,l.name,l.slug,l.status,l.visibility,l.max_members,:role role,
                   c.season,ct.public_id template_id
            from leagues l join competitions c on c.id=l.competition_id
            join competition_templates ct on ct.id=c.template_id where l.id=:league
            """,
            {"league": invite["league_id"], "role": invite["role"]},
        )
    ) or {}


@router.put("/pools/{pool_id}/draft-order", response_model=dict, tags=["draft"])
async def set_draft_order(
    pool_id: UUID, payload: DraftOrderWrite, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    pool, _ = await repo.pool(pool_id, user, commissioner=True)
    members = await repo.ensure_members(pool["league_id"], payload.member_ids)
    await repo.execute(
        "update pools set draft_order=cast(:order as jsonb) where id=:pool",
        {"order": json_value([str(value) for value in payload.member_ids]), "pool": pool["id"]},
    )
    await repo.execute(
        """
        insert into draft_states (pool_id,status,current_pick_number,current_round)
        values (:pool,'pending',1,1) on conflict (pool_id) do nothing
        """,
        {"pool": pool["id"]},
    )
    for member in members:
        await repo.execute(
            """
            insert into roster_slots (pool_id,league_member_id,slot_number)
            select :pool,:member,n from generate_series(1,:size) n on conflict do nothing
            """,
            {"pool": pool["id"], "member": member["id"], "size": pool["roster_size"]},
        )
    return {"pool_id": pool_id, "draft_order": payload.member_ids}


@router.post("/pools/{pool_id}/preassignments", response_model=Message, tags=["draft"])
async def preassign_team(
    pool_id: UUID, payload: PreassignmentWrite, session: Session, user: CurrentUser
) -> Message:
    repo = Repository(session)
    pool, access = await repo.pool(pool_id, user, commissioner=True)
    member_id = await repo.member_id(pool["league_id"], payload.member_id)
    team_id = await repo.pool_team_id(pool["id"], payload.team_id)
    slot = row(
        await repo.execute(
            """
            select id from roster_slots where pool_id=:pool and league_member_id=:member
              and slot_number=:slot for update
            """,
            {"pool": pool["id"], "member": member_id, "slot": payload.slot_number},
        )
    )
    if not slot:
        raise HTTPException(status_code=422, detail="Roster slot not found")
    await repo.execute(
        """
        insert into roster_entries (roster_slot_id,pool_team_id,acquired_via)
        values (:slot,:team,:via)
        """,
        {"slot": slot["id"], "team": team_id, "via": "keeper" if payload.keeper else "preassigned"},
    )
    await repo.audit(
        pool["league_id"],
        access["profile_id"],
        "preassign",
        "roster_entry",
        after=payload.model_dump(mode="json"),
    )
    return Message(detail="Team preassigned")


@router.post("/pools/{pool_id}/draft/start", response_model=DraftStateOut, tags=["draft"])
async def start_draft(
    pool_id: UUID, payload: DraftStart, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    pool, access = await repo.pool(pool_id, user, commissioner=True)
    draft_format = payload.format or access["settings"].get("format", "linear")
    if draft_format not in {"linear", "snake"}:
        raise HTTPException(status_code=422, detail="Invalid draft format")
    return await DraftService(repo).start(pool, draft_format, access["profile_id"])


@router.get("/pools/{pool_id}/draft", response_model=DraftStateOut, tags=["draft"])
async def get_draft(pool_id: UUID, session: Session, user: CurrentUser) -> dict[str, Any]:
    repo = Repository(session)
    pool, _ = await repo.pool(pool_id, user)
    return await DraftService(repo).state(pool["id"])


@router.post(
    "/pools/{pool_id}/draft/picks",
    response_model=DraftStateOut,
    status_code=201,
    tags=["draft"],
)
async def make_pick(
    pool_id: UUID, payload: DraftPickCreate, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    pool, access = await repo.pool(pool_id, user)
    return await DraftService(repo).pick(pool, access, payload)


@router.post("/leagues/{league_id}/roster-corrections", response_model=Message, tags=["rosters"])
async def correct_roster(
    league_id: UUID, payload: RosterCorrection, session: Session, user: CurrentUser
) -> Message:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    member = await repo.member_id(access["league_id"], payload.member_id)
    target = row(
        await repo.execute(
            """
            select rs.id slot_id,pt.id pool_team_id,re.public_id old_entry,
                   t.public_id old_team
            from teams t2 join pool_teams pt on pt.team_id=t2.id
            join pools p on p.id=pt.pool_id and p.league_id=:league
            join roster_slots rs on rs.pool_id=p.id and rs.league_member_id=:member
              and rs.slot_number=:slot
            left join roster_entries re on re.roster_slot_id=rs.id and re.valid_until is null
            left join pool_teams oldpt on oldpt.id=re.pool_team_id
            left join teams t on t.id=oldpt.team_id
            where t2.public_id=:team
            """,
            {
                "league": access["league_id"],
                "member": member,
                "slot": payload.slot_number,
                "team": payload.team_id,
            },
        )
    )
    if not target:
        raise HTTPException(status_code=422, detail="Team and slot do not share a pool")
    await repo.execute(
        "update roster_entries set valid_until=now() where roster_slot_id=:slot and valid_until is null",
        {"slot": target["slot_id"]},
    )
    await repo.execute(
        """
        update roster_entries set valid_until=now()
        where pool_team_id=:team and valid_until is null
        """,
        {"team": target["pool_team_id"]},
    )
    entry = row(
        await repo.execute(
            """
            insert into roster_entries (roster_slot_id,pool_team_id,acquired_via)
            values (:slot,:team,'admin') returning public_id
            """,
            {"slot": target["slot_id"], "team": target["pool_team_id"]},
        )
    )
    await repo.audit(
        access["league_id"],
        access["profile_id"],
        "correct",
        "roster_entry",
        entity_public_id=entry["public_id"] if entry else None,
        before={"team_id": target["old_team"]} if target["old_team"] else None,
        after={"team_id": payload.team_id, "member_id": payload.member_id},
        reason=payload.reason,
    )
    return Message(detail="Roster corrected")


@router.post("/leagues/{league_id}/pick-corrections", response_model=Message, tags=["draft"])
async def correct_pick(
    league_id: UUID, payload: PickCorrection, session: Session, user: CurrentUser
) -> Message:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    pick = row(
        await repo.execute(
            """
            select dp.*,t.public_id old_team,p.id pool_internal
            from draft_picks dp join pools p on p.id=dp.pool_id
            join pool_teams pt on pt.id=dp.pool_team_id join teams t on t.id=pt.team_id
            where dp.public_id=:pick and p.league_id=:league for update of dp
            """,
            {"pick": payload.pick_id, "league": access["league_id"]},
        )
    )
    if not pick:
        raise HTTPException(status_code=404, detail="Draft pick not found")
    new_team = await repo.pool_team_id(pick["pool_internal"], payload.team_id)
    await repo.execute(
        """
        update roster_entries set valid_until=now()
        where pool_team_id=:team and valid_until is null
          and roster_slot_id<>:pick_slot
        """,
        {"team": new_team, "pick_slot": pick["roster_slot_id"]},
    )
    await repo.execute(
        "update draft_picks set pool_team_id=:team where id=:id",
        {"team": new_team, "id": pick["id"]},
    )
    await repo.execute(
        "update roster_entries set pool_team_id=:team where roster_slot_id=:slot and valid_until is null",
        {"team": new_team, "slot": pick["roster_slot_id"]},
    )
    await repo.audit(
        access["league_id"],
        access["profile_id"],
        "correct",
        "draft_pick",
        entity_public_id=payload.pick_id,
        before={"team_id": pick["old_team"]},
        after={"team_id": payload.team_id},
        reason=payload.reason,
    )
    return Message(detail="Pick corrected")


@router.get("/leagues/{league_id}/readiness", response_model=ReadinessOut, tags=["seasons"])
async def season_readiness(
    league_id: UUID, session: Session, user: CurrentUser
) -> ReadinessOut:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    return await SyncService(repo).readiness(access["league_id"])


@router.post("/leagues/{league_id}/bootstrap", tags=["seasons"])
async def bootstrap_season(
    league_id: UUID, payload: BootstrapRequest, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    return await SyncService(repo).bootstrap(access["league_id"], payload.provider_params)


@router.post("/leagues/{league_id}/sync", response_model=SyncOut, tags=["sync"])
async def commissioner_sync(
    league_id: UUID, payload: SyncRequest, session: Session, user: CurrentUser
) -> SyncOut:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    return await SyncService(repo).sync_matches(access["league_id"], payload)


@router.post("/leagues/{league_id}/recompute", tags=["sync"])
async def commissioner_recompute(
    league_id: UUID, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    first_kickoff = (
        await repo.execute(
            """
            select min(m.kickoff_at) from matches m
            join leagues l on l.competition_id=m.competition_id where l.id=:league
            """,
            {"league": access["league_id"]},
        )
    ).scalar_one_or_none()
    affected = await SyncService(repo).recompute(access["league_id"], first_kickoff)
    return {"status": "succeeded", "affected_matches": affected}


@router.get("/leagues/{league_id}/sync-status", tags=["sync"])
async def sync_status(league_id: UUID, session: Session, user: CurrentUser) -> list[dict[str, Any]]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    return rows(
        await repo.execute(
            """
            select ss.public_id id,ss.resource_type,ss.status,ss.last_attempt_at,
              ss.last_success_at,ss.next_attempt_at,ss.rate_limit_remaining,
              ss.rate_limit_reset_at,ss.last_error
            from sync_status ss join leagues l on l.competition_id=ss.competition_id
            where l.id=:league
            """,
            {"league": access["league_id"]},
        )
    )


@router.post("/internal/sync-and-score", response_model=SyncOut, tags=["internal"])
async def internal_sync(
    league_id: UUID,
    payload: SyncRequest,
    session: Session,
    x_internal_token: Annotated[str | None, Header()] = None,
) -> SyncOut:
    expected = get_settings().internal_sync_token
    if not expected or not x_internal_token or not secrets.compare_digest(expected, x_internal_token):
        raise HTTPException(status_code=401, detail="Invalid internal token")
    league_internal = (
        await Repository(session).execute(
            "select id from leagues where public_id=:id", {"id": league_id}
        )
    ).scalar_one_or_none()
    if league_internal is None:
        raise HTTPException(status_code=404, detail="League not found")
    return await SyncService(Repository(session)).sync_matches(int(league_internal), payload)


@router.get("/leagues/{league_id}/bonuses", response_model=list[BonusOut], tags=["bonuses"])
async def list_bonuses(
    league_id: UUID, session: Session, user: CurrentUser
) -> list[dict[str, Any]]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    return rows(
        await repo.execute(
            """
            select b.public_id id,b.current_member_public_id member_id,
              b.current_owner_display_name display_name,t.public_id team_id,
              m.public_id match_id,b.bonus_type,b.phase,b.points,b.reason,b.awarded_at,b.revoked_at
            from v_bonuses_current_owner b join teams t on t.id=b.team_id
            left join matches m on m.id=b.match_id
            where b.league_id=:league and b.team_id is not null order by b.awarded_at desc
            """,
            {"league": access["league_id"]},
        )
    )


async def _validate_bonus_config(
    repo: Repository, league_id: int, bonus_type: str, phase: str
) -> None:
    scoring = (
        await repo.execute(
            """
            select ct.scoring_config from leagues l
            join competitions c on c.id=l.competition_id
            join competition_templates ct on ct.id=c.template_id where l.id=:league
            """,
            {"league": league_id},
        )
    ).scalar_one()
    if bonus_type not in scoring.get("manual_bonus_defaults", {}):
        raise HTTPException(status_code=422, detail="Unknown configured bonus type")
    phases = {
        str(value.get("key") or value.get("name"))
        for value in scoring.get("phases", [])
    }
    if phase != "overall" and phase not in phases:
        raise HTTPException(status_code=422, detail="Unknown scoring phase")


@router.post("/leagues/{league_id}/bonuses", response_model=BonusOut, status_code=201, tags=["bonuses"])
async def create_bonus(
    league_id: UUID, payload: BonusWrite, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    await _validate_bonus_config(
        repo, access["league_id"], payload.bonus_type, payload.phase
    )
    team = row(
        await repo.execute(
            """
            select distinct t.id from teams t join pool_teams pt on pt.team_id=t.id
            join pools p on p.id=pt.pool_id
            where t.public_id=:team and p.league_id=:league
            """,
            {"team": payload.team_id, "league": access["league_id"]},
        )
    )
    if not team:
        raise HTTPException(status_code=422, detail="Team is not in this league")
    match_id = await _league_match_id(repo, access["league_id"], payload.match_id)
    item = row(
        await repo.execute(
            """
            insert into bonuses
              (league_id,team_id,match_id,bonus_type,phase,points,reason,awarded_by_profile_id)
            values (:league,:team_internal,:match_internal,:type,:phase,:points,:reason,:profile)
            returning public_id
            """,
            {
                "league": access["league_id"],
                "team_internal": team["id"],
                "match_internal": match_id,
                "type": payload.bonus_type,
                "phase": payload.phase,
                "points": payload.points,
                "reason": payload.reason,
                "profile": access["profile_id"],
            },
        )
    )
    assert item
    return row(
        await repo.execute(
            """
            select b.public_id id,b.current_member_public_id member_id,
              b.current_owner_display_name display_name,t.public_id team_id,
              m.public_id match_id,b.bonus_type,b.phase,b.points,b.reason,b.awarded_at,b.revoked_at
            from v_bonuses_current_owner b join teams t on t.id=b.team_id
            left join matches m on m.id=b.match_id where b.public_id=:id
            """,
            {"id": item["public_id"]},
        )
    ) or {}


@router.delete("/leagues/{league_id}/bonuses/{bonus_id}", response_model=Message, tags=["bonuses"])
async def revoke_bonus(
    league_id: UUID, bonus_id: UUID, session: Session, user: CurrentUser
) -> Message:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    await _validate_bonus_config(
        repo, access["league_id"], payload.bonus_type, payload.phase
    )
    result = await repo.execute(
        """
        update bonuses set revoked_at=now()
        where public_id=:bonus and league_id=:league and revoked_at is null
        """,
        {"bonus": bonus_id, "league": access["league_id"]},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Active bonus not found")
    return Message(detail="Bonus revoked")


@router.put(
    "/leagues/{league_id}/bonuses/{bonus_id}", response_model=BonusOut, tags=["bonuses"]
)
async def update_bonus(
    league_id: UUID,
    bonus_id: UUID,
    payload: BonusWrite,
    session: Session,
    user: CurrentUser,
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    team = row(
        await repo.execute(
            """
            select distinct t.id from teams t join pool_teams pt on pt.team_id=t.id
            join pools p on p.id=pt.pool_id
            where t.public_id=:team and p.league_id=:league
            """,
            {"team": payload.team_id, "league": access["league_id"]},
        )
    )
    if not team:
        raise HTTPException(status_code=422, detail="Team is not in this league")
    match_id = await _league_match_id(repo, access["league_id"], payload.match_id)
    item = row(
        await repo.execute(
            """
            update bonuses set league_member_id=null,team_id=:team_internal,
              match_id=:match_internal,
              bonus_type=:type,phase=:phase,points=:points,reason=:reason
            where public_id=:bonus and league_id=:league and revoked_at is null
            returning public_id
            """,
            {
                "bonus": bonus_id,
                "league": access["league_id"],
                "team_internal": team["id"],
                "match_internal": match_id,
                "type": payload.bonus_type,
                "phase": payload.phase,
                "points": payload.points,
                "reason": payload.reason,
            },
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Active bonus not found")
    return row(
        await repo.execute(
            """
            select b.public_id id,b.current_member_public_id member_id,
              b.current_owner_display_name display_name,t.public_id team_id,
              m.public_id match_id,b.bonus_type,b.phase,b.points,b.reason,b.awarded_at,b.revoked_at
            from v_bonuses_current_owner b join teams t on t.id=b.team_id
            left join matches m on m.id=b.match_id where b.public_id=:id
            """,
            {"id": item["public_id"]},
        )
    ) or {}


@router.post("/leagues/{league_id}/ranking-lists", response_model=RankingListOut, tags=["rankings"])
async def create_ranking_list(
    league_id: UUID, payload: RankingListCreate, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    pool = row(
        await repo.execute(
            "select id,public_id from pools where public_id=:pool and league_id=:league",
            {"pool": payload.pool_id, "league": access["league_id"]},
        )
    )
    if not pool:
        raise HTTPException(status_code=422, detail="Pool not found")
    item = row(
        await repo.execute(
            """
            insert into ranking_lists (league_id,pool_id,name)
            values (:league,:pool,:name)
            returning public_id id,:pool_public pool_id,name,status,locked_at
            """,
            {
                "league": access["league_id"],
                "pool": pool["id"],
                "pool_public": pool["public_id"],
                "name": payload.name,
            },
        )
    )
    assert item
    item["rows"] = []
    return item


@router.get(
    "/leagues/{league_id}/ranking-lists",
    response_model=list[RankingListOut],
    tags=["rankings"],
)
async def list_ranking_lists(
    league_id: UUID, session: Session, user: CurrentUser
) -> list[dict[str, Any]]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    identifiers = [
        value["public_id"]
        for value in rows(
            await repo.execute(
                """
                select public_id from ranking_lists
                where league_id=:league order by created_at desc
                """,
                {"league": access["league_id"]},
            )
        )
    ]
    return [
        await _ranking_list(repo, identifier, access["league_id"])
        for identifier in identifiers
    ]


async def _ranking_list(repo: Repository, list_id: UUID, league_id: int) -> dict[str, Any]:
    item = row(
        await repo.execute(
            """
            select rl.id internal_id,rl.public_id id,p.public_id pool_id,rl.name,rl.status,rl.locked_at
            from ranking_lists rl join pools p on p.id=rl.pool_id
            where rl.public_id=:list and rl.league_id=:league
            """,
            {"list": list_id, "league": league_id},
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Ranking list not found")
    item["rows"] = rows(
        await repo.execute(
            """
            select r.public_id id,lm.public_id member_id,t.public_id team_id,t.name,r.rank,
              r.source_value
            from ranking_list_rows r join league_members lm on lm.id=r.league_member_id
            join pool_teams pt on pt.id=r.pool_team_id join teams t on t.id=pt.team_id
            where r.ranking_list_id=:list order by lm.public_id,r.rank
            """,
            {"list": item["internal_id"]},
        )
    )
    item.pop("internal_id")
    return item


@router.get(
    "/leagues/{league_id}/ranking-lists/{list_id}",
    response_model=RankingListOut,
    tags=["rankings"],
)
async def get_ranking_list(
    league_id: UUID, list_id: UUID, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    return await _ranking_list(repo, list_id, access["league_id"])


@router.post(
    "/leagues/{league_id}/ranking-lists/{list_id}/import",
    response_model=RankingListOut,
    tags=["rankings"],
)
async def import_rankings(
    league_id: UUID,
    list_id: UUID,
    payload: RankingImport,
    session: Session,
    user: CurrentUser,
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    listing = row(
        await repo.execute(
            """
            select rl.id,rl.pool_id,rl.status from ranking_lists rl
            where rl.public_id=:list and rl.league_id=:league for update
            """,
            {"list": list_id, "league": access["league_id"]},
        )
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Ranking list not found")
    if listing["status"] == "locked":
        raise HTTPException(status_code=409, detail="Ranking list is locked")
    member = await repo.member_id(access["league_id"], payload.member_id)
    if access["member_id"] != member and access["role"] not in {"owner", "commissioner"}:
        raise HTTPException(status_code=403, detail="Cannot import another member's rankings")
    parsed = parse_ranking_rows(payload)
    teams = rows(
        await repo.execute(
            """
            select pt.id,t.name,t.tla,t.provider_team_id from pool_teams pt
            join teams t on t.id=pt.team_id where pt.pool_id=:pool
            """,
            {"pool": listing["pool_id"]},
        )
    )
    lookup: dict[str, int] = {}
    for team in teams:
        for value in (team["name"], team["tla"], team["provider_team_id"]):
            if value:
                lookup[str(value).strip().casefold()] = team["id"]
    mapped: list[tuple[int, int, str]] = []
    unknown: list[str] = []
    for rank_value, team_value in parsed:
        team_id = lookup.get(team_value.casefold())
        if team_id is None:
            unknown.append(team_value)
        else:
            mapped.append((rank_value, team_id, team_value))
    if unknown:
        raise HTTPException(status_code=422, detail={"unmapped_teams": unknown})
    await repo.execute(
        "delete from ranking_list_rows where ranking_list_id=:list and league_member_id=:member",
        {"list": listing["id"], "member": member},
    )
    for rank_value, team_id, source in mapped:
        await repo.execute(
            """
            insert into ranking_list_rows
              (ranking_list_id,league_member_id,pool_team_id,rank,source_value)
            values (:list,:member,:team,:rank,:source)
            """,
            {
                "list": listing["id"],
                "member": member,
                "team": team_id,
                "rank": rank_value,
                "source": source,
            },
        )
    return await _ranking_list(repo, list_id, access["league_id"])


@router.post(
    "/leagues/{league_id}/ranking-lists/{list_id}/lock",
    response_model=RankingListOut,
    tags=["rankings"],
)
async def lock_ranking_list(
    league_id: UUID, list_id: UUID, session: Session, user: CurrentUser
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    result = await repo.execute(
        """
        update ranking_lists set status='locked',locked_at=now(),locked_by_profile_id=:profile
        where public_id=:list and league_id=:league and status='draft'
        """,
        {"list": list_id, "league": access["league_id"], "profile": access["profile_id"]},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="Ranking list is missing or already locked")
    return await _ranking_list(repo, list_id, access["league_id"])


@router.delete(
    "/leagues/{league_id}/ranking-lists/{list_id}",
    response_model=Message,
    tags=["rankings"],
)
async def delete_ranking_list(
    league_id: UUID, list_id: UUID, session: Session, user: CurrentUser
) -> Message:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    result = await repo.execute(
        """
        delete from ranking_lists
        where public_id=:list and league_id=:league and status='draft'
        """,
        {"list": list_id, "league": access["league_id"]},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="Only draft ranking lists can be deleted")
    return Message(detail="Ranking list deleted")


@router.get(
    "/leagues/{league_id}/standings", response_model=StandingsOut, tags=["standings"]
)
async def standings(
    league_id: UUID,
    session: Session,
    user: CurrentUser,
    phase: str = Query(default="overall"),
) -> dict[str, Any]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    phases = await league_phases(repo, access["league_id"])
    metadata = next((value for value in phases if value["key"] == phase), None)
    if metadata is None:
        raise HTTPException(status_code=422, detail="Unknown scoring phase")
    return {
        "phase": metadata,
        "entries": await compute_standings(repo, access["league_id"], phase),
    }


@router.get("/leagues/{league_id}/rosters", tags=["rosters"])
async def rosters(league_id: UUID, session: Session, user: CurrentUser) -> list[dict[str, Any]]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    return rows(
        await repo.execute(
            """
            select lm.public_id member_id,pr.display_name,p.public_id pool_id,p.name pool_name,
              rs.slot_number,t.public_id team_id,t.name team_name,re.acquired_via,
              re.valid_from,re.valid_until
            from roster_slots rs join pools p on p.id=rs.pool_id
            join league_members lm on lm.id=rs.league_member_id
            join profiles pr on pr.id=lm.profile_id
            left join roster_entries re on re.roster_slot_id=rs.id and re.valid_until is null
            left join pool_teams pt on pt.id=re.pool_team_id left join teams t on t.id=pt.team_id
            where p.league_id=:league order by p.ordinal,lm.joined_at,rs.slot_number
            """,
            {"league": access["league_id"]},
        )
    )


@router.get("/leagues/{league_id}/match-log", tags=["scoring"])
async def match_log(
    league_id: UUID,
    session: Session,
    user: CurrentUser,
    phase: str | None = None,
) -> list[dict[str, Any]]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    return rows(
        await repo.execute(
            """
            select se.public_id id,m.public_id match_id,m.kickoff_at,m.matchday,
              t.public_id team_id,t.name team_name,se.current_member_public_id member_id,
              se.current_owner_display_name display_name,se.phase,
              se.event_type,se.points,se.details,se.source_result_version
            from v_scoring_events_current_owner se join matches m on m.id=se.match_id
            join teams t on t.id=se.team_id
            where se.league_id=:league and se.superseded_at is null
              and (:phase is null or se.phase=:phase)
            order by m.kickoff_at desc,se.id
            """,
            {"league": access["league_id"], "phase": phase},
        )
    )


@router.get("/leagues/{league_id}/snapshot-audit", tags=["scoring"])
async def snapshot_audit(
    league_id: UUID, session: Session, user: CurrentUser
) -> list[dict[str, Any]]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    return rows(
        await repo.execute(
            """
            select ts.public_id id,p.public_id pool_id,ts.kickoff_at,ts.source_match_version,
              ts.computed_at,jsonb_agg(jsonb_build_object(
                'team_id',t.public_id,'team_name',t.name,'position',r.position,
                'played',r.played,'points',r.points) order by r.position) rows
            from table_snapshots ts join pools p on p.id=ts.pool_id
            join table_snapshot_rows r on r.snapshot_id=ts.id join teams t on t.id=r.team_id
            where p.league_id=:league
            group by ts.id,ts.public_id,p.public_id,ts.kickoff_at,
              ts.source_match_version,ts.computed_at order by ts.kickoff_at desc
            """,
            {"league": access["league_id"]},
        )
    )


@router.get("/leagues/{league_id}/audit", response_model=list[AuditEntry], tags=["audit"])
async def audit_log(
    league_id: UUID, session: Session, user: CurrentUser
) -> list[dict[str, Any]]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user, commissioner=True)
    return rows(
        await repo.execute(
            """
            select public_id id,action,entity_type,entity_public_id entity_id,
              before_data before,after_data after,reason,created_at
            from audit_events where league_id=:league order by created_at desc
            """,
            {"league": access["league_id"]},
        )
    )


@router.get("/leagues/{league_id}/analytics/teams", tags=["analytics"])
async def team_analytics(
    league_id: UUID, session: Session, user: CurrentUser
) -> list[dict[str, Any]]:
    repo = Repository(session)
    await repo.league_access(league_id, user)
    return rows(
        await repo.execute(
            """
            select *,case when scored_matches=0 then 0
              else round(points/scored_matches,2) end ppg
            from v_team_scoring_analytics where league_public_id=:league
            order by points desc,team_name
            """,
            {"league": league_id},
        )
    )


@router.get("/leagues/{league_id}/analytics/members", tags=["analytics"])
async def member_analytics(
    league_id: UUID, session: Session, user: CurrentUser
) -> list[dict[str, Any]]:
    repo = Repository(session)
    await repo.league_access(league_id, user)
    return rows(
        await repo.execute(
            """
            select *,case when scored_matches=0 then 0
              else round(total_points/scored_matches,2) end ppg
            from v_member_scoring_analytics where league_public_id=:league
            order by total_points desc,display_name
            """,
            {"league": league_id},
        )
    )


@router.get("/leagues/{league_id}/analytics/matchweeks", tags=["analytics"])
async def matchweek_analytics(
    league_id: UUID, session: Session, user: CurrentUser
) -> list[dict[str, Any]]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    return rows(
        await repo.execute(
            """
            with weekly as (
              select se.current_member_public_id member_id,
                se.current_owner_display_name display_name,m.matchday,
                sum(se.points) points,
                sum(se.points) filter (
                  where se.event_type not in ('win','draw','loss')
                ) upset_points
              from v_scoring_events_current_owner se join matches m on m.id=se.match_id
              where se.league_id=:league and se.superseded_at is null
                and se.current_member_public_id is not null
              group by se.current_member_public_id,se.current_owner_display_name,m.matchday
            )
            select *,sum(points) over (partition by member_id order by matchday) cumulative_points
            from weekly order by matchday,points desc
            """,
            {"league": access["league_id"]},
        )
    )


@router.get("/leagues/{league_id}/analytics/upsets", tags=["analytics"])
async def upset_analytics(
    league_id: UUID, session: Session, user: CurrentUser
) -> list[dict[str, Any]]:
    repo = Repository(session)
    access = await repo.league_access(league_id, user)
    return rows(
        await repo.execute(
            """
            select se.public_id id,m.public_id match_id,m.kickoff_at,m.matchday,
              t.public_id team_id,t.name team_name,se.current_member_public_id member_id,
              se.current_owner_display_name display_name,se.points,se.details
            from v_scoring_events_current_owner se join matches m on m.id=se.match_id
            join teams t on t.id=se.team_id
            where se.league_id=:league
              and se.event_type not in ('win','draw','loss')
              and se.superseded_at is null
            order by se.points desc,m.kickoff_at desc
            """,
            {"league": access["league_id"]},
        )
    )
