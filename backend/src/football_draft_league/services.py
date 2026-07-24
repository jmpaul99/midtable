import csv
import io
import json
from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from football_draft_league.repository import Repository, row, rows
from football_draft_league.schemas import DraftPickCreate, RankingImport
from football_draft_league.scoring import LeaderboardEntry, LeaderboardRung, rank_leaderboard


def _draft_member(order: list[str], pick: int, draft_format: str) -> tuple[str, int, int]:
    if not order:
        raise HTTPException(status_code=409, detail="Draft order is not configured")
    round_number = ((pick - 1) // len(order)) + 1
    round_pick = ((pick - 1) % len(order)) + 1
    index = round_pick - 1
    if draft_format == "snake" and round_number % 2 == 0:
        index = len(order) - 1 - index
    return order[index], round_number, round_pick


class DraftService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    async def state(self, pool_internal_id: int) -> dict[str, Any]:
        state = row(
            await self.repo.execute(
                """
                select ds.public_id id, p.public_id pool_id, ds.status,
                       ds.current_pick_number, ds.current_round, lm.public_id current_member_id,
                       ds.version
                from draft_states ds join pools p on p.id=ds.pool_id
                left join league_members lm on lm.id=ds.current_member_id
                where ds.pool_id=:pool_id
                """,
                {"pool_id": pool_internal_id},
            )
        )
        if not state:
            raise HTTPException(status_code=404, detail="Draft has not been created")
        state["picks"] = rows(
            await self.repo.execute(
                """
                select dp.public_id id, dp.pick_number, dp.round_number,
                       dp.round_pick_number, lm.public_id member_id, t.public_id team_id,
                       t.name team_name, dp.picked_at
                from draft_picks dp
                join league_members lm on lm.id=dp.league_member_id
                join pool_teams pt on pt.id=dp.pool_team_id join teams t on t.id=pt.team_id
                where dp.pool_id=:pool_id order by dp.pick_number
                """,
                {"pool_id": pool_internal_id},
            )
        )
        return state

    async def start(
        self, pool: dict[str, Any], draft_format: str, profile_id: int
    ) -> dict[str, Any]:
        order = [str(value) for value in pool["draft_order"]]
        first_member: int | None = None
        first_pick = 1
        while first_pick <= len(order):
            first, _, _ = _draft_member(order, first_pick, draft_format)
            candidate = await self.repo.member_id(pool["league_id"], UUID(first))
            available = int(
                (
                    await self.repo.execute(
                        """
                        select count(*) from roster_slots rs
                        left join roster_entries re on re.roster_slot_id=rs.id
                          and re.valid_until is null
                        where rs.pool_id=:pool and rs.league_member_id=:member and re.id is null
                        """,
                        {"pool": pool["id"], "member": candidate},
                    )
                ).scalar_one()
            )
            if available:
                first_member = candidate
                break
            first_pick += 1
        if first_member is None:
            raise HTTPException(status_code=409, detail="No draftable roster slots remain")
        result = await self.repo.execute(
            """
            insert into draft_states
              (pool_id, status, current_pick_number, current_round, current_member_id,
               draft_format, started_at)
            values (:pool_id, 'running', :pick, 1, :member_id, :format, now())
            on conflict (pool_id) do update set status='running', current_pick_number=:pick,
              current_round=1, current_member_id=:member_id,
              draft_format=:format, version=draft_states.version+1,
              started_at=now(), completed_at=null
            where draft_states.status in ('pending','paused','cancelled')
            """,
            {
                "pool_id": pool["id"],
                "member_id": first_member,
                "pick": first_pick,
                "format": draft_format,
            },
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=409, detail="Draft cannot be restarted in its current state")
        await self.repo.execute(
            """
            update leagues set status='drafting',
              settings=jsonb_set(settings, '{draft_format}', to_jsonb(cast(:format as text)), true)
            where id=:league_id and status='setup'
            """,
            {"league_id": pool["league_id"], "format": draft_format},
        )
        return await self.state(pool["id"])

    async def pick(
        self,
        pool: dict[str, Any],
        access: dict[str, Any],
        payload: DraftPickCreate,
    ) -> dict[str, Any]:
        state = row(
            await self.repo.execute(
                "select * from draft_states where pool_id=:pool_id for update",
                {"pool_id": pool["id"]},
            )
        )
        if not state:
            raise HTTPException(status_code=409, detail="Draft is not running")
        existing = row(
            await self.repo.execute(
                """
                select dp.public_id from draft_picks dp
                where dp.draft_state_id=:state_id and dp.idempotency_key=:key
                """,
                {"state_id": state["id"], "key": payload.idempotency_key},
            )
        )
        if existing:
            return await self.state(pool["id"])
        if state["status"] != "running":
            raise HTTPException(status_code=409, detail="Draft is not running")
        if state["version"] != payload.expected_version:
            raise HTTPException(status_code=409, detail="Draft state changed; refresh and retry")
        if state["current_member_id"] != access["member_id"]:
            raise HTTPException(status_code=403, detail="It is not your turn")

        pool_team_id = await self.repo.pool_team_id(pool["id"], payload.team_id)
        slot = row(
            await self.repo.execute(
                """
                select rs.id from roster_slots rs
                left join roster_entries re on re.roster_slot_id=rs.id and re.valid_until is null
                where rs.pool_id=:pool_id and rs.league_member_id=:member_id and re.id is null
                order by rs.slot_number for update of rs skip locked limit 1
                """,
                {"pool_id": pool["id"], "member_id": access["member_id"]},
            )
        )
        if not slot:
            raise HTTPException(status_code=409, detail="No vacant roster slot")
        pick_number = state["current_pick_number"]
        order = [str(value) for value in pool["draft_order"]]
        draft_format = state["draft_format"]
        _, round_number, round_pick = _draft_member(order, pick_number, draft_format)
        try:
            pick = row(
                await self.repo.execute(
                    """
                    insert into draft_picks
                      (draft_state_id, pool_id, pick_number, round_number, round_pick_number,
                       league_member_id, pool_team_id, roster_slot_id, idempotency_key)
                    values (:state_id,:pool_id,:pick,:round,:round_pick,:member,:team,:slot,:key)
                    returning public_id id, pick_number, round_number, round_pick_number, picked_at
                    """,
                    {
                        "state_id": state["id"],
                        "pool_id": pool["id"],
                        "pick": pick_number,
                        "round": round_number,
                        "round_pick": round_pick,
                        "member": access["member_id"],
                        "team": pool_team_id,
                        "slot": slot["id"],
                        "key": payload.idempotency_key,
                    },
                )
            )
            await self.repo.execute(
                """
                insert into roster_entries (roster_slot_id, pool_team_id, acquired_via)
                values (:slot,:team,'draft')
                """,
                {"slot": slot["id"], "team": pool_team_id},
            )
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Team or pick was already taken") from exc

        vacant_slots = int(
            (
                await self.repo.execute(
                    """
                    select count(*) from roster_slots rs
                    left join roster_entries re on re.roster_slot_id=rs.id and re.valid_until is null
                    where rs.pool_id=:pool_id and re.id is null
                    """,
                    {"pool_id": pool["id"]},
                )
            ).scalar_one()
        )
        next_pick = pick_number + 1
        if vacant_slots == 0:
            await self.repo.execute(
                """
                update draft_states set status='completed', current_pick_number=:next_pick,
                  completed_at=now(), current_member_id=null, version=version+1
                where id=:id
                """,
                {"next_pick": next_pick, "id": state["id"]},
            )
            await self.repo.execute(
                """
                update leagues l set status='active'
                where l.id=:league and not exists (
                  select 1 from pools p left join draft_states ds on ds.pool_id=p.id
                  where p.league_id=l.id and coalesce(ds.status,'pending')<>'completed'
                )
                """,
                {"league": pool["league_id"]},
            )
        else:
            next_member: int | None = None
            next_round = 1
            for _ in range(len(order)):
                next_public, next_round, _ = _draft_member(order, next_pick, draft_format)
                candidate = await self.repo.member_id(pool["league_id"], UUID(next_public))
                candidate_vacancies = int(
                    (
                        await self.repo.execute(
                            """
                            select count(*) from roster_slots rs
                            left join roster_entries re on re.roster_slot_id=rs.id
                              and re.valid_until is null
                            where rs.pool_id=:pool and rs.league_member_id=:member and re.id is null
                            """,
                            {"pool": pool["id"], "member": candidate},
                        )
                    ).scalar_one()
                )
                if candidate_vacancies:
                    next_member = candidate
                    break
                next_pick += 1
            if next_member is None:
                raise HTTPException(status_code=409, detail="Draft order has no eligible member")
            await self.repo.execute(
                """
                update draft_states set current_pick_number=:next_pick, current_round=:round,
                  current_member_id=:member, version=version+1 where id=:id
                """,
                {
                    "next_pick": next_pick,
                    "round": next_round,
                    "member": next_member,
                    "id": state["id"],
                },
            )
        assert pick is not None
        return await self.state(pool["id"])


def parse_ranking_rows(payload: RankingImport) -> list[tuple[int, str]]:
    text = payload.text.strip()
    # Plain newline-separated team names (no CSV delimiter)
    if "," not in text and "\t" not in text and ";" not in text and "|" not in text:
        names = [line.strip() for line in text.splitlines() if line.strip()]
        if payload.has_header and names and names[0].lower() in {"team", "name", "rank"}:
            names = names[1:]
        parsed = [(i, name) for i, name in enumerate(names, 1)]
        if not parsed:
            raise HTTPException(status_code=422, detail="No ranking rows found")
        if len({rank for rank, _ in parsed}) != len(parsed):
            raise HTTPException(status_code=422, detail="Ranking contains duplicate ranks")
        return parsed

    sample = text[:4096]
    delimiter = payload.delimiter
    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
        except csv.Error:
            delimiter = ","
    raw_rows = list(csv.reader(io.StringIO(payload.text), delimiter=delimiter))
    if payload.has_header:
        raw_rows = raw_rows[1:]
    parsed = []
    for ordinal, values in enumerate(raw_rows, 1):
        if not values or payload.team_column >= len(values):
            continue
        team = values[payload.team_column].strip()
        if not team:
            continue
        rank = ordinal
        if payload.rank_column is not None and payload.rank_column < len(values):
            try:
                rank = int(values[payload.rank_column])
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"Invalid rank on row {ordinal}") from exc
        parsed.append((rank, team))
    if not parsed:
        raise HTTPException(status_code=422, detail="No ranking rows found")
    if len({rank for rank, _ in parsed}) != len(parsed):
        raise HTTPException(status_code=422, detail="Ranking contains duplicate ranks")
    return parsed


def split_payouts(
    ranked: list[tuple[int, UUID]], payouts: list[dict[str, Any]]
) -> dict[UUID, Decimal]:
    by_rank = {int(item["rank"]): Decimal(str(item["amount"])) for item in payouts}
    result = {member_id: Decimal(0) for _, member_id in ranked}
    groups: dict[int, list[UUID]] = defaultdict(list)
    for rank, member_id in ranked:
        groups[rank].append(member_id)
    for rank, members in groups.items():
        occupied = range(rank, rank + len(members))
        pot = sum((by_rank.get(place, Decimal(0)) for place in occupied), Decimal(0))
        share = pot / len(members)
        for member in members:
            result[member] = share
    return result


def normalize_phase(definition: dict[str, Any]) -> dict[str, Any]:
    key = str(definition.get("key") or definition.get("name") or "phase")
    matchweek_range = definition.get("matchweek_range")
    if matchweek_range is None and definition.get("first_matchweek") is not None:
        matchweek_range = [
            int(definition["first_matchweek"]),
            int(definition["last_matchweek"]),
        ]
    stage_in = definition.get("stage_in")
    return {
        "key": key,
        "name": str(definition.get("label") or definition.get("name") or key),
        "matchweek_range": matchweek_range,
        "stage_in": stage_in,
    }


def team_available(current_owner: dict[str, Any] | None) -> bool:
    return current_owner is None


def attribute_points_by_current_owner(
    team_points: dict[UUID, Decimal],
    current_owners: dict[UUID, UUID | None],
) -> dict[UUID, Decimal]:
    totals: dict[UUID, Decimal] = defaultdict(Decimal)
    for team_id, points in team_points.items():
        owner_id = current_owners.get(team_id)
        if owner_id is not None:
            totals[owner_id] += points
    return dict(totals)


def phase_completeness(
    definition: dict[str, Any], matches: list[dict[str, Any]]
) -> dict[str, Any]:
    phase = normalize_phase(definition)
    selected = matches
    if phase["matchweek_range"]:
        first, last = phase["matchweek_range"]
        selected = [
            match for match in matches if match.get("matchday") is not None
            and first <= int(match["matchday"]) <= last
        ]
    elif phase["stage_in"]:
        stages = set(phase["stage_in"])
        selected = [match for match in matches if match.get("stage") in stages]
    finished = sum(match.get("status") == "finished" for match in selected)
    matching = len(selected)
    return {
        **phase,
        "matching_matches": matching,
        "finished_matches": finished,
        "remaining_matches": matching - finished,
        "is_final": matching > 0 and finished == matching,
    }


async def league_phases(repo: Repository, league_id: int) -> list[dict[str, Any]]:
    config = (
        await repo.execute(
            """
            select ct.scoring_config from leagues l
            join competitions c on c.id=l.competition_id
            join competition_templates ct on ct.id=c.template_id where l.id=:league
            """,
            {"league": league_id},
        )
    ).scalar_one()
    matches = rows(
        await repo.execute(
            """
            select distinct m.id,m.matchday,m.stage,m.status
            from pools p join pool_teams home_pool on home_pool.pool_id=p.id
            join matches m on m.home_team_id=home_pool.team_id
            join pool_teams away_pool
              on away_pool.pool_id=p.id and away_pool.team_id=m.away_team_id
            where p.league_id=:league and p.scoring_enabled=true
            """,
            {"league": league_id},
        )
    )
    definitions = config.get("phases", [])
    overall = phase_completeness(
        {"key": "overall", "name": "Overall"}, matches
    )
    return [overall, *(phase_completeness(value, matches) for value in definitions)]


async def compute_standings(
    repo: Repository, league_id: int, phase: str
) -> list[dict[str, Any]]:
    league = row(
        await repo.execute(
            """
            select l.settings,ct.tiebreak_config,ct.payout_config,ct.scoring_config
            from leagues l join competitions c on c.id=l.competition_id
            join competition_templates ct on ct.id=c.template_id where l.id=:league_id
            """,
            {"league_id": league_id},
        )
    )
    members = rows(
        await repo.execute(
            """
            select lm.public_id member_id,p.display_name
            from league_members lm join profiles p on p.id=lm.profile_id
            where lm.league_id=:league_id and lm.status='active'
            order by lm.joined_at,lm.id
            """,
            {"league_id": league_id},
        )
    )
    event_rows = rows(
        await repo.execute(
            """
            select current_member_public_id member_id,event_type,points
            from v_scoring_events_current_owner
            where league_id=:league and superseded_at is null
              and current_member_public_id is not null
              and (:phase='overall' or phase=:phase)
            """,
            {"league": league_id, "phase": phase},
        )
    )
    bonus_rows = rows(
        await repo.execute(
            """
            select current_member_public_id member_id,bonus_type,points
            from v_bonuses_current_owner
            where league_id=:league and revoked_at is null
              and current_member_public_id is not null
              and (:phase='overall' or phase=:phase)
            """,
            {"league": league_id, "phase": phase},
        )
    )
    events_by_member: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    bonuses_by_member: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for event in event_rows:
        events_by_member[event["member_id"]].append(event)
    for bonus in bonus_rows:
        bonuses_by_member[bonus["member_id"]].append(bonus)

    scoring_config = (league or {}).get("scoring_config") or {}
    thresholds = scoring_config.get("upset", {}).get("thresholds", [])
    upset_keys = [
        str(item.get("key") or "upset") for item in thresholds if isinstance(item, dict)
    ]
    legacy = {
        "total_points": {"metric": "total_points", "direction": "desc"},
        "upset_points": {
            "metric": "event_points",
            "event_types": list(dict.fromkeys([*upset_keys, "upset"])),
            "direction": "desc",
        },
        "win_count": {
            "metric": "event_count",
            "event_types": ["win"],
            "direction": "desc",
        },
    }
    rung_configs = [
        legacy.get(value, value) if isinstance(value, str) else value
        for value in ((league or {}).get("tiebreak_config") or ["total_points"])
    ]
    rungs = [
        LeaderboardRung(
            metric=config["metric"],
            event_types=tuple(config.get("event_types", [])),
            bonus_type_keys=tuple(config.get("bonus_type_keys", [])),
            direction=config.get("direction", "desc"),
        )
        for config in rung_configs
    ]

    def metric_value(
        config: dict[str, Any],
        member_events: list[dict[str, Any]],
        member_bonuses: list[dict[str, Any]],
    ) -> Decimal | int:
        metric = config["metric"]
        event_types = set(config.get("event_types", []))
        bonus_types = set(config.get("bonus_type_keys", []))
        selected_events = [
            value for value in member_events if value["event_type"] in event_types
        ]
        selected_bonuses = [
            value for value in member_bonuses if value["bonus_type"] in bonus_types
        ]
        if metric == "total_points":
            return sum(
                (Decimal(str(value["points"])) for value in [*member_events, *member_bonuses]),
                Decimal(0),
            )
        if metric == "event_points":
            return sum(
                (Decimal(str(value["points"])) for value in selected_events), Decimal(0)
            )
        if metric == "event_count":
            return len(selected_events)
        if metric == "bonus_points":
            return sum(
                (Decimal(str(value["points"])) for value in selected_bonuses), Decimal(0)
            )
        if metric == "bonus_count":
            return len(selected_bonuses)
        raise ValueError(f"unsupported leaderboard metric: {metric}")

    audit_values: dict[int, list[dict[str, Any]]] = {}
    entries: list[LeaderboardEntry] = []
    for index, member in enumerate(members):
        member_events = events_by_member[member["member_id"]]
        member_bonuses = bonuses_by_member[member["member_id"]]
        values = tuple(
            metric_value(config, member_events, member_bonuses) for config in rung_configs
        )
        total_points = metric_value(
            {"metric": "total_points"}, member_events, member_bonuses
        )
        upset_points = sum(
            (
                Decimal(str(value["points"]))
                for value in member_events
                if value["event_type"] in {*upset_keys, "upset"}
            ),
            Decimal(0),
        )
        win_count = sum(value["event_type"] == "win" for value in member_events)
        entries.append(
            LeaderboardEntry(index, Decimal(total_points), upset_points, win_count, values)
        )
        audit_values[index] = [
            {**config, "value": value} for config, value in zip(rung_configs, values)
        ]

    ranked = rank_leaderboard(entries, rungs)
    rank_members = [(value.rank, members[value.entry.member_id]["member_id"]) for value in ranked]
    payout_config = [
        item
        for item in ((league or {}).get("payout_config") or [])
        if item.get("phase", "overall") == phase
    ]
    payout = split_payouts(rank_members, payout_config)
    return [
        {
            "member_id": members[value.entry.member_id]["member_id"],
            "display_name": members[value.entry.member_id]["display_name"],
            "rank": value.rank,
            "total_points": value.entry.total_points,
            "upset_points": value.entry.upset_points,
            "win_count": value.entry.win_count,
            "payout": payout[members[value.entry.member_id]["member_id"]],
            "metric_values": audit_values[value.entry.member_id],
        }
        for value in ranked
    ]


def json_value(value: Any) -> str:
    return json.dumps(value, default=str)
