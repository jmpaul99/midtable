import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Result, text
from sqlalchemy.ext.asyncio import AsyncSession

from football_draft_league.auth import AuthenticatedUser


def rows(result: Result[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in result.mappings().all()]


def row(result: Result[Any]) -> dict[str, Any] | None:
    value = result.mappings().first()
    return dict(value) if value else None


class Repository:
    """Small transaction-bound repository; API code never exposes bigint keys."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute(
        self, statement: str, params: Mapping[str, Any] | None = None
    ) -> Result[Any]:
        return await self.session.execute(text(statement), params or {})

    async def profile(self, user: AuthenticatedUser, display_name: str | None = None) -> dict[str, Any]:
        result = await self.execute(
            """
            insert into profiles (auth_user_id, display_name)
            values (:auth_id, :display_name)
            on conflict (auth_user_id) do update set
              display_name = case
                when profiles.display_name = profiles.auth_user_id::text
                then excluded.display_name else profiles.display_name end
            returning id, public_id, display_name
            """,
            {
                "auth_id": user.id,
                "display_name": display_name
                or user.claims.get("user_metadata", {}).get("display_name")
                or (user.email.split("@")[0] if user.email else str(user.id)),
            },
        )
        return dict(result.mappings().one())

    async def league_access(
        self,
        league_id: UUID,
        user: AuthenticatedUser,
        *,
        commissioner: bool = False,
    ) -> dict[str, Any]:
        result = await self.execute(
            """
            select l.id league_id, l.public_id, l.status, l.settings, l.owner_profile_id,
                   lm.id member_id, lm.public_id member_public_id, lm.role, p.id profile_id
            from leagues l
            join league_members lm on lm.league_id = l.id and lm.status = 'active'
            join profiles p on p.id = lm.profile_id
            where l.public_id = :league_id and p.auth_user_id = :auth_id
            """,
            {"league_id": league_id, "auth_id": user.id},
        )
        access = row(result)
        if not access:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
        if commissioner and access["role"] not in {"owner", "commissioner"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Commissioner required")
        return access

    async def template_internal_id(self, public_id: UUID) -> int:
        value = (
            await self.execute(
                "select id from competition_templates where public_id=:id", {"id": public_id}
            )
        ).scalar_one_or_none()
        if value is None:
            raise HTTPException(status_code=404, detail="Competition template not found")
        return int(value)

    async def pool(
        self, pool_id: UUID, user: AuthenticatedUser, *, commissioner: bool = False
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        pool = row(
            await self.execute(
                """
                select p.*, l.public_id league_public_id
                from pools p join leagues l on l.id=p.league_id
                where p.public_id=:pool_id
                """,
                {"pool_id": pool_id},
            )
        )
        if not pool:
            raise HTTPException(status_code=404, detail="Pool not found")
        access = await self.league_access(pool["league_public_id"], user, commissioner=commissioner)
        return pool, access

    async def member_id(self, league_id: int, member_public_id: UUID) -> int:
        value = (
            await self.execute(
                """
                select id from league_members
                where league_id=:league_id and public_id=:member_id and status='active'
                """,
                {"league_id": league_id, "member_id": member_public_id},
            )
        ).scalar_one_or_none()
        if value is None:
            raise HTTPException(status_code=422, detail="Member is not active in this league")
        return int(value)

    async def pool_team_id(self, pool_id: int, team_public_id: UUID) -> int:
        value = (
            await self.execute(
                """
                select pt.id from pool_teams pt join teams t on t.id=pt.team_id
                where pt.pool_id=:pool_id and t.public_id=:team_id
                """,
                {"pool_id": pool_id, "team_id": team_public_id},
            )
        ).scalar_one_or_none()
        if value is None:
            raise HTTPException(status_code=422, detail="Team is not available in this pool")
        return int(value)

    async def ensure_members(
        self, league_id: int, public_ids: Sequence[UUID]
    ) -> list[dict[str, Any]]:
        result = rows(
            await self.execute(
                """
                select id, public_id from league_members
                where league_id=:league_id and public_id = any(:member_ids) and status='active'
                """,
                {"league_id": league_id, "member_ids": list(public_ids)},
            )
        )
        by_public = {item["public_id"]: item for item in result}
        if set(by_public) != set(public_ids):
            raise HTTPException(status_code=422, detail="Draft order contains an inactive member")
        return [by_public[value] for value in public_ids]

    async def audit(
        self,
        league_id: int,
        profile_id: int,
        action: str,
        entity_type: str,
        *,
        entity_public_id: UUID | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> None:
        await self.execute(
            """
            insert into audit_events
              (league_id, actor_profile_id, action, entity_type, entity_public_id,
               before_data, after_data, reason)
            values
              (:league_id, :actor, :action, :entity_type, :entity_id,
               cast(:before as jsonb), cast(:after as jsonb), :reason)
            """,
            {
                "league_id": league_id,
                "actor": profile_id,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_public_id,
                "before": json.dumps(before, default=str) if before is not None else None,
                "after": json.dumps(after, default=str) if after is not None else None,
                "reason": reason,
            },
        )
