from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from football_draft_league.config import get_settings
from football_draft_league.db import async_session_factory
from football_draft_league.providers import provider_for
from football_draft_league.providers.base import RateLimit
from football_draft_league.repository import Repository, row, rows
from football_draft_league.schemas import ReadinessOut, SyncOut, SyncRequest
from football_draft_league.services import normalize_phase


STATUS_MAP = {
    "SCHEDULED": "scheduled",
    "TIMED": "timed",
    "IN_PLAY": "in_play",
    "PAUSED": "paused",
    "FINISHED": "finished",
    "POSTPONED": "postponed",
    "SUSPENDED": "suspended",
    "CANCELLED": "cancelled",
}


def _winner(payload: dict[str, Any]) -> str | None:
    value = payload.get("score", {}).get("winner")
    return {"HOME_TEAM": "home", "AWAY_TEAM": "away", "DRAW": "draw"}.get(value)


def _score(payload: dict[str, Any], side: str) -> int | None:
    value = payload.get("score", {}).get("fullTime", {}).get(side)
    return int(value) if value is not None else None


class SyncService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    async def competition(self, league_id: int) -> dict[str, Any]:
        value = row(
            await self.repo.execute(
                """
                select c.*, ct.provider, ct.provider_competition_code, ct.pool_definitions,
                       ct.scoring_config, ct.tiebreak_config,
                       l.provider_params league_provider_params
                from leagues l join competitions c on c.id=l.competition_id
                join competition_templates ct on ct.id=c.template_id where l.id=:league_id
                """,
                {"league_id": league_id},
            )
        )
        if not value:
            raise HTTPException(status_code=404, detail="Competition not found")
        return value

    async def readiness(self, league_id: int) -> ReadinessOut:
        competition = await self.competition(league_id)
        errors: list[str] = []
        warnings: list[str] = []
        pools = rows(
            await self.repo.execute(
                "select * from pools where league_id=:league_id order by ordinal",
                {"league_id": league_id},
            )
        )
        if not pools:
            errors.append("No pools configured")
        if not get_settings().football_data_api_token and competition["provider"] == "football-data.org":
            errors.append("Provider API token is not configured")
        normalized_phases = [
            normalize_phase(value)
            for value in competition["scoring_config"].get("phases", [])
        ]
        phases = sorted(
            (value for value in normalized_phases if value["matchweek_range"] is not None),
            key=lambda value: value["matchweek_range"][0],
        )
        for previous, current in zip(phases, phases[1:], strict=False):
            if previous["matchweek_range"][1] >= current["matchweek_range"][0]:
                errors.append("Scoring phases overlap")
                break
        active_members = int(
            (
                await self.repo.execute(
                    """
                    select count(*) from league_members
                    where league_id=:league and status='active'
                    """,
                    {"league": league_id},
                )
            ).scalar_one()
        )
        for pool in pools:
            if not pool["provider_competition_code"]:
                errors.append(f"Pool {pool['name']} has no provider competition code")
            count = int(
                (
                    await self.repo.execute(
                        "select count(*) from pool_teams where pool_id=:pool_id",
                        {"pool_id": pool["id"]},
                    )
                ).scalar_one()
            )
            if count == 0:
                warnings.append(f"Pool {pool['name']} has not been bootstrapped")
            elif count < active_members * pool["roster_size"]:
                errors.append(
                    f"Pool {pool['name']} has fewer teams than required roster slots"
                )
            order = pool["draft_order"]
            if order and len(order) != active_members:
                errors.append(f"Pool {pool['name']} draft order does not include every member")
        return ReadinessOut(ready=not errors, errors=errors, warnings=warnings)

    async def bootstrap(self, league_id: int, provider_params: dict[str, Any]) -> dict[str, Any]:
        competition = await self.competition(league_id)
        pools = rows(
            await self.repo.execute(
                "select * from pools where league_id=:league_id order by ordinal",
                {"league_id": league_id},
            )
        )
        effective_params = {
            **competition.get("league_provider_params", {}),
            **provider_params,
        }
        await self.repo.execute(
            """
            update leagues set provider_params=provider_params || cast(:params as jsonb)
            where id=:league
            """,
            {"params": self._json(provider_params), "league": league_id},
        )
        provider = provider_for(competition["provider"], get_settings())
        imported = 0
        try:
            for pool in pools:
                pool_params = {**effective_params, **pool.get("provider_params", {})}
                season = int(
                    pool_params.get("season") or str(competition["season"]).split("/")[0]
                )
                response = await provider.teams([pool["provider_competition_code"]], season)
                for item in response.items:
                    team = row(
                        await self.repo.execute(
                            """
                            insert into teams
                              (competition_id, provider_team_id, name, short_name, tla, crest_url,
                               venue, provider_payload)
                            values (:competition,:provider_id,:name,:short_name,:tla,:crest,:venue,
                                    cast(:payload as jsonb))
                            on conflict (competition_id, provider_team_id) do update set
                              name=excluded.name, short_name=excluded.short_name, tla=excluded.tla,
                              crest_url=excluded.crest_url, venue=excluded.venue,
                              provider_payload=excluded.provider_payload, is_active=true
                            returning id
                            """,
                            {
                                "competition": competition["id"],
                                "provider_id": str(item["id"]),
                                "name": item["name"],
                                "short_name": item.get("shortName"),
                                "tla": item.get("tla"),
                                "crest": item.get("crest"),
                                "venue": item.get("venue"),
                                "payload": self._json(item),
                            },
                        )
                    )
                    assert team
                    await self.repo.execute(
                        """
                        insert into pool_teams (pool_id, team_id)
                        values (:pool,:team) on conflict (pool_id, team_id) do nothing
                        """,
                        {"pool": pool["id"], "team": team["id"]},
                    )
                    imported += 1
        finally:
            await provider.close()
        return {"status": "succeeded", "teams_imported": imported}

    async def sync_matches(
        self, league_id: int, payload: SyncRequest
    ) -> SyncOut:
        competition = await self.competition(league_id)
        lock_key = int(competition["id"])
        locked = bool(
            (
                await self.repo.execute(
                    "select pg_try_advisory_xact_lock(73194, :key)", {"key": lock_key}
                )
            ).scalar_one()
        )
        if not locked:
            raise HTTPException(status_code=409, detail="A sync is already running")
        retry_at = (
            await self.repo.execute(
                """
                select rate_limit_reset_at from sync_status
                where competition_id=:competition and resource_type='matches'
                  and rate_limit_remaining=0 and rate_limit_reset_at>now()
                """,
                {"competition": competition["id"]},
            )
        ).scalar_one_or_none()
        if retry_at is not None:
            raise HTTPException(
                status_code=429,
                detail=f"Provider rate limit is active until {retry_at.isoformat()}",
            )
        await self._status(competition["id"], "running")
        codes = [
            item["provider_competition_code"]
            for item in rows(
                await self.repo.execute(
                    """
                    select distinct provider_competition_code from pools
                    where league_id=:league and scoring_enabled=true
                    """,
                    {"league": league_id},
                )
            )
        ]
        provider = provider_for(competition["provider"], get_settings())
        synced = changed = 0
        earliest_change: datetime | None = None
        rate = RateLimit()
        try:
            response = await provider.matches(
                codes,
                date_from=payload.date_from,
                date_to=payload.date_to,
                statuses=payload.statuses,
            )
            rate = response.rate_limit
            for item in response.items:
                home = await self._team_id(competition["id"], str(item["homeTeam"]["id"]))
                away = await self._team_id(competition["id"], str(item["awayTeam"]["id"]))
                if home is None or away is None:
                    continue
                previous = row(
                    await self.repo.execute(
                        """
                        select id, kickoff_at, matchday, stage, home_team_id, away_team_id,
                               status, home_score, away_score, winner, result_version
                        from matches where competition_id=:competition and provider_match_id=:provider
                        """,
                        {"competition": competition["id"], "provider": str(item["id"])},
                    )
                )
                status = STATUS_MAP.get(item.get("status"), "scheduled")
                home_score, away_score, winner = (
                    _score(item, "home"),
                    _score(item, "away"),
                    _winner(item),
                )
                result_changed = bool(
                    previous
                    and previous["status"] == "finished"
                    and (previous["home_score"], previous["away_score"], previous["winner"])
                    != (home_score, away_score, winner)
                )
                version = int(previous["result_version"]) + int(result_changed) if previous else 1
                kickoff = datetime.fromisoformat(item["utcDate"].replace("Z", "+00:00"))
                chronology_changed = bool(previous and previous["kickoff_at"] != kickoff)
                scoring_context_changed = bool(
                    previous
                    and (
                        previous["matchday"] != item.get("matchday")
                        or previous["stage"] != item.get("stage")
                        or previous["home_team_id"] != home
                        or previous["away_team_id"] != away
                    )
                )
                provider_updated = item.get("lastUpdated")
                if isinstance(provider_updated, str):
                    provider_updated = datetime.fromisoformat(
                        provider_updated.replace("Z", "+00:00")
                    )
                await self.repo.execute(
                    """
                    insert into matches
                      (competition_id, provider_match_id, matchday, stage, home_team_id,
                       away_team_id, kickoff_at, status, home_score, away_score, winner,
                       duration, result_version, provider_updated_at, provider_payload)
                    values (:competition,:provider,:matchday,:stage,:home,:away,:kickoff,:status,
                            :home_score,:away_score,:winner,:duration,:version,:updated,
                            cast(:payload as jsonb))
                    on conflict (competition_id, provider_match_id) do update set
                      matchday=excluded.matchday, stage=excluded.stage,
                      home_team_id=excluded.home_team_id, away_team_id=excluded.away_team_id,
                      kickoff_at=excluded.kickoff_at, status=excluded.status,
                      home_score=excluded.home_score, away_score=excluded.away_score,
                      winner=excluded.winner, duration=excluded.duration,
                      result_version=excluded.result_version,
                      provider_updated_at=excluded.provider_updated_at,
                      provider_payload=excluded.provider_payload
                    """,
                    {
                        "competition": competition["id"],
                        "provider": str(item["id"]),
                        "matchday": item.get("matchday"),
                        "stage": item.get("stage"),
                        "home": home,
                        "away": away,
                        "kickoff": kickoff,
                        "status": status,
                        "home_score": home_score,
                        "away_score": away_score,
                        "winner": winner,
                        "duration": item.get("score", {}).get("duration"),
                        "version": version,
                        "updated": provider_updated,
                        "payload": self._json(item),
                    },
                )
                synced += 1
                if result_changed:
                    changed += 1
                if result_changed or chronology_changed or scoring_context_changed:
                    cascade_at = (
                        min(previous["kickoff_at"], kickoff) if previous else kickoff
                    )
                    earliest_change = min(earliest_change or cascade_at, cascade_at)
            affected = await self.recompute(league_id, earliest_change)
            await self._status(competition["id"], "succeeded", rate)
            return SyncOut(
                status="succeeded",
                synced_matches=synced,
                changed_results=changed,
                affected_matches=affected,
                rate_limit_remaining=rate.remaining,
                rate_limit_reset_at=rate.reset_at,
            )
        except Exception as exc:
            provider_rate = getattr(exc, "rate_limit", None)
            if isinstance(provider_rate, RateLimit):
                rate = provider_rate
            rate_limited = bool(getattr(exc, "rate_limited", False))
            await self._status(
                competition["id"],
                "rate_limited" if rate_limited else "failed",
                rate,
                str(exc),
            )
            if rate_limited:
                raise HTTPException(status_code=429, detail=str(exc)) from exc
            raise
        finally:
            await provider.close()

    async def recompute(self, league_id: int, starts_at: datetime | None = None) -> int:
        await self.repo.execute(
            "select pg_advisory_xact_lock(73195, :league)", {"league": league_id}
        )
        params: dict[str, Any] = {"league": league_id}
        cutoff = "and m.kickoff_at >= :starts_at" if starts_at else ""
        if starts_at:
            params["starts_at"] = starts_at
            await self.repo.execute(
                """
                update scoring_events set superseded_at=now()
                where league_id=:league and superseded_at is null and match_id in
                  (select id from matches where kickoff_at>=:starts_at)
                """,
                params,
            )
        matches = rows(
            await self.repo.execute(
                f"""
                select distinct m.* from matches m
                join pool_teams ph on ph.team_id=m.home_team_id
                join pools p on p.id=ph.pool_id and p.league_id=:league and p.scoring_enabled=true
                join pool_teams pa on pa.pool_id=p.id and pa.team_id=m.away_team_id
                where m.status='finished' {cutoff}
                order by m.kickoff_at, m.id
                """,
                params,
            )
        )
        snapshot_cache: dict[tuple[int, datetime], int] = {}
        for match in matches:
            pools = rows(
                await self.repo.execute(
                    """
                    select p.* from pools p join pool_teams h on h.pool_id=p.id
                    join pool_teams a on a.pool_id=p.id
                    where p.league_id=:league and p.scoring_enabled=true
                      and h.team_id=:home and a.team_id=:away
                    """,
                    {"league": league_id, "home": match["home_team_id"], "away": match["away_team_id"]},
                )
            )
            for pool in pools:
                snapshot_id = await self._snapshot(
                    pool,
                    match,
                    snapshot_cache,
                    force_new=starts_at is not None,
                )
                await self._score_match(league_id, pool, match, snapshot_id)
        return len(matches)

    async def _snapshot(
        self,
        pool: dict[str, Any],
        match: dict[str, Any],
        cache: dict[tuple[int, datetime], int],
        *,
        force_new: bool,
    ) -> int:
        cache_key = (pool["id"], match["kickoff_at"])
        if cache_key in cache:
            return cache[cache_key]
        if not force_new:
            existing = (
                await self.repo.execute(
                    """
                    select id from table_snapshots
                    where pool_id=:pool and kickoff_at=:kickoff
                    order by source_match_version desc limit 1
                    """,
                    {"pool": pool["id"], "kickoff": match["kickoff_at"]},
                )
            ).scalar_one_or_none()
            if existing:
                cache[cache_key] = int(existing)
                return int(existing)
        next_version = int(
            (
                await self.repo.execute(
                    """
                    select greatest(
                      :match_version,
                      coalesce(max(source_match_version),0)+1
                    )
                    from table_snapshots
                    where pool_id=:pool and kickoff_at=:kickoff
                    """,
                    {
                        "match_version": match["result_version"],
                        "pool": pool["id"],
                        "kickoff": match["kickoff_at"],
                    },
                )
            ).scalar_one()
        )
        snapshot = row(
            await self.repo.execute(
                """
                insert into table_snapshots
                  (competition_id, pool_id, kickoff_at, source_match_version)
                values (:competition,:pool,:kickoff,:version) returning id
                """,
                {
                    "competition": match["competition_id"],
                    "pool": pool["id"],
                    "kickoff": match["kickoff_at"],
                    "version": next_version,
                },
            )
        )
        assert snapshot
        scoring_config = (
            await self.repo.execute(
                """
                select ct.scoring_config from pools p join leagues l on l.id=p.league_id
                join competitions c on c.id=l.competition_id
                join competition_templates ct on ct.id=c.template_id where p.id=:pool
                """,
                {"pool": pool["id"]},
            )
        ).scalar_one()
        order_fields = {
            "points": "(won*3+drawn) desc",
            "goal_difference": "gf-ga desc",
            "goals_for": "gf desc",
            "name": "name asc",
        }
        configured = scoring_config.get(
            "table_tiebreaks", ["points", "goal_difference", "goals_for", "name"]
        )
        if unknown := set(configured) - set(order_fields):
            raise HTTPException(status_code=422, detail=f"Unsupported table tiebreaks: {unknown}")
        ordering = ", ".join(order_fields[value] for value in configured) + ", team_id"
        await self.repo.execute(
            f"""
            with prior as (
              select pt.team_id,t.name,
                count(m.id)::int played,
                count(*) filter (where (m.home_team_id=pt.team_id and m.winner='home')
                                  or (m.away_team_id=pt.team_id and m.winner='away'))::int won,
                count(*) filter (where m.winner='draw')::int drawn,
                coalesce(sum(case when m.home_team_id=pt.team_id then m.home_score
                                  else m.away_score end),0)::int gf,
                coalesce(sum(case when m.home_team_id=pt.team_id then m.away_score
                                  else m.home_score end),0)::int ga
              from pool_teams pt join teams t on t.id=pt.team_id left join matches m
                on (m.home_team_id=pt.team_id or m.away_team_id=pt.team_id)
                and m.status='finished' and m.kickoff_at<:kickoff
              where pt.pool_id=:pool group by pt.team_id,t.name
            ), ranked as (
              select *, (won*3 + drawn) points,
                row_number() over (order by {ordering})::int pos
              from prior
            )
            insert into table_snapshot_rows
              (snapshot_id, team_id, position, played, won, drawn, lost,
               goals_for, goals_against, points)
            select :snapshot, team_id, pos, played, won, drawn, played-won-drawn, gf, ga, points
            from ranked
            """,
            {
                "snapshot": snapshot["id"],
                "pool": pool["id"],
                "kickoff": match["kickoff_at"],
            },
        )
        cache[cache_key] = int(snapshot["id"])
        return int(snapshot["id"])

    async def _score_match(
        self, league_id: int, pool: dict[str, Any], match: dict[str, Any], snapshot_id: int
    ) -> None:
        config = row(
            await self.repo.execute(
                """
                select ct.scoring_config from leagues l join competitions c on c.id=l.competition_id
                join competition_templates ct on ct.id=c.template_id where l.id=:league
                """,
                {"league": league_id},
            )
        ) or {"scoring_config": {}}
        scoring = config["scoring_config"]
        phases = scoring.get("phases", [])
        phase = "overall"
        phase_definition: dict[str, Any] = {}
        for definition in phases:
            normalized = normalize_phase(definition)
            matchweek_range = normalized["matchweek_range"]
            stage_in = normalized["stage_in"]
            if (
                matchweek_range
                and match["matchday"] is not None
                and matchweek_range[0] <= match["matchday"] <= matchweek_range[1]
            ) or (stage_in and match["stage"] in stage_in):
                phase = normalized["key"]
                phase_definition = definition
                break
        result_points = phase_definition.get(
            "result_points",
            scoring.get("result_points", {"win": 3, "draw": 1, "loss": 0}),
        )
        upset = phase_definition.get("upset", scoring.get("upset", {}))
        positions = {
            value["team_id"]: value
            for value in rows(
                await self.repo.execute(
                    """
                    select team_id,position,played from table_snapshot_rows
                    where snapshot_id=:snapshot and team_id in (:home,:away)
                    """,
                    {
                        "snapshot": snapshot_id,
                        "home": match["home_team_id"],
                        "away": match["away_team_id"],
                    },
                )
            )
        }
        for side, team_id in (("home", match["home_team_id"]), ("away", match["away_team_id"])):
            result = (
                "draw"
                if match["winner"] == "draw"
                else "win"
                if match["winner"] == side
                else "loss"
            )
            await self.repo.execute(
                """
                insert into scoring_events
                  (league_id,match_id,team_id,snapshot_id,phase,event_type,points,
                   source_result_version,details)
                values (:league,:match,:team,:snapshot,:phase,:event_type,:points,:version,
                        cast(:details as jsonb))
                on conflict (league_id,match_id,team_id,phase,event_type)
                  where superseded_at is null
                do update set points=excluded.points,
                  source_result_version=excluded.source_result_version,
                  details=excluded.details,snapshot_id=excluded.snapshot_id
                """,
                {
                    "league": league_id,
                    "match": match["id"],
                    "team": team_id,
                    "snapshot": snapshot_id,
                    "phase": phase,
                    "event_type": result,
                    "points": Decimal(str(result_points[result])),
                    "version": match["result_version"],
                    "details": self._json({"result": result}),
                },
            )
            opponent_id = match["away_team_id"] if side == "home" else match["home_team_id"]
            upset_points = Decimal(0)
            upset_event_type: str | None = None
            team_row = positions.get(team_id)
            opponent_row = positions.get(opponent_id)
            minimum_played = int(upset.get("minimum_matches_played", 0))
            if (
                team_row
                and opponent_row
                and team_row["played"] >= minimum_played
                and opponent_row["played"] >= minimum_played
            ):
                gap = int(team_row["position"]) - int(opponent_row["position"])
                for threshold in upset.get("thresholds", []):
                    maximum = threshold.get("maximum_position_gap")
                    if (
                        threshold.get("result") == result
                        and gap >= int(threshold["minimum_position_gap"])
                        and (maximum is None or gap <= int(maximum))
                    ):
                        upset_points = Decimal(str(threshold["bonus"]))
                        upset_event_type = str(threshold.get("key") or "upset")
                        break
            if upset_points and upset_event_type:
                await self.repo.execute(
                    """
                    insert into scoring_events
                      (league_id,match_id,team_id,snapshot_id,phase,event_type,points,
                       source_result_version,details)
                    values (:league,:match,:team,:snapshot,:phase,:event_type,:points,:version,
                            cast(:details as jsonb))
                    on conflict (league_id,match_id,team_id,phase,event_type)
                      where superseded_at is null
                    do update set points=excluded.points,
                      source_result_version=excluded.source_result_version,
                      details=excluded.details,snapshot_id=excluded.snapshot_id
                    """,
                    {
                        "league": league_id,
                        "match": match["id"],
                        "team": team_id,
                        "snapshot": snapshot_id,
                        "phase": phase,
                        "event_type": upset_event_type,
                        "points": upset_points,
                        "version": match["result_version"],
                        "details": self._json(
                            {
                                "result": result,
                                "position_gap": int(team_row["position"])
                                - int(opponent_row["position"]),
                            }
                        ),
                    },
                )

    async def _team_id(self, competition_id: int, provider_id: str) -> int | None:
        value = (
            await self.repo.execute(
                """
                select id from teams where competition_id=:competition
                  and provider_team_id=:provider
                """,
                {"competition": competition_id, "provider": provider_id},
            )
        ).scalar_one_or_none()
        return int(value) if value is not None else None

    async def _status(
        self,
        competition_id: int,
        status: str,
        rate: RateLimit | None = None,
        error: str | None = None,
    ) -> None:
        rate = rate or RateLimit()
        next_attempt = rate.reset_at
        if next_attempt is None and rate.retry_after_seconds is not None:
            next_attempt = datetime.now(UTC) + timedelta(seconds=rate.retry_after_seconds)
        async with async_session_factory() as session:
            async with session.begin():
                await Repository(session).execute(
                    """
                    insert into sync_status
                      (competition_id, resource_type, status, last_attempt_at, last_success_at,
                       next_attempt_at, rate_limit_remaining, rate_limit_reset_at, last_error)
                    values (:competition,'matches',:status,now(),
                            case when :status='succeeded' then now() end,:next_attempt,
                            :remaining,:reset,:error)
                    on conflict (competition_id,resource_type) do update set
                      status=excluded.status, last_attempt_at=excluded.last_attempt_at,
                      last_success_at=coalesce(
                        excluded.last_success_at,sync_status.last_success_at
                      ),
                      next_attempt_at=excluded.next_attempt_at,
                      rate_limit_remaining=coalesce(
                        excluded.rate_limit_remaining,sync_status.rate_limit_remaining
                      ),
                      rate_limit_reset_at=coalesce(
                        excluded.rate_limit_reset_at,sync_status.rate_limit_reset_at
                      ),
                      last_error=excluded.last_error
                    """,
                    {
                        "competition": competition_id,
                        "status": status,
                        "next_attempt": next_attempt,
                        "remaining": rate.remaining,
                        "reset": rate.reset_at,
                        "error": error,
                    },
                )

    @staticmethod
    def _json(value: Any) -> str:
        import json

        return json.dumps(value, default=str)
