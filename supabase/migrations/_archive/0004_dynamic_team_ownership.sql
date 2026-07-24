begin;

alter table public.leagues
  add column if not exists provider_params jsonb not null default '{}'::jsonb;
alter table public.pools
  add column if not exists provider_params jsonb not null default '{}'::jsonb;

alter table public.scoring_events
  alter column league_member_id drop not null;
alter table public.bonuses
  alter column league_member_id drop not null;
alter table public.bonuses
  add constraint bonuses_team_required check (team_id is not null) not valid;

drop index if exists public.scoring_events_active_natural_key;
with duplicate_events as (
  select id, row_number() over (
    partition by league_id, match_id, team_id, phase, event_type
    order by source_result_version desc, updated_at desc, id desc
  ) as duplicate_number
  from public.scoring_events
  where superseded_at is null
)
update public.scoring_events se
set superseded_at = timezone('utc', now())
from duplicate_events d
where se.id = d.id and d.duplicate_number > 1;
create unique index scoring_events_active_team_key
  on public.scoring_events
  (league_id, match_id, team_id, phase, event_type)
  where superseded_at is null;

create or replace view public.v_scoring_events_current_owner
with (security_invoker = true)
as
select
  se.*,
  current_owner.league_member_id as current_league_member_id,
  current_owner.member_public_id as current_member_public_id,
  current_owner.display_name as current_owner_display_name
from public.scoring_events se
left join lateral (
  select rs.league_member_id, lm.public_id as member_public_id, pr.display_name
  from public.pool_teams pt
  join public.pools p on p.id = pt.pool_id and p.league_id = se.league_id
  join public.roster_entries re
    on re.pool_team_id = pt.id and re.valid_until is null
  join public.roster_slots rs on rs.id = re.roster_slot_id and rs.pool_id = p.id
  join public.league_members lm on lm.id = rs.league_member_id and lm.status = 'active'
  join public.profiles pr on pr.id = lm.profile_id
  where pt.team_id = se.team_id
  order by re.valid_from desc, re.id desc
  limit 1
) current_owner on true;

create or replace view public.v_bonuses_current_owner
with (security_invoker = true)
as
select
  b.*,
  current_owner.league_member_id as current_league_member_id,
  current_owner.member_public_id as current_member_public_id,
  current_owner.display_name as current_owner_display_name
from public.bonuses b
left join lateral (
  select rs.league_member_id, lm.public_id as member_public_id, pr.display_name
  from public.pool_teams pt
  join public.pools p on p.id = pt.pool_id and p.league_id = b.league_id
  join public.roster_entries re
    on re.pool_team_id = pt.id and re.valid_until is null
  join public.roster_slots rs on rs.id = re.roster_slot_id and rs.pool_id = p.id
  join public.league_members lm on lm.id = rs.league_member_id and lm.status = 'active'
  join public.profiles pr on pr.id = lm.profile_id
  where pt.team_id = b.team_id
  order by re.valid_from desc, re.id desc
  limit 1
) current_owner on true;

create or replace view public.v_team_scoring_analytics
with (security_invoker = true)
as
select
  l.public_id as league_public_id,
  t.public_id as team_public_id,
  t.name as team_name,
  count(distinct se.match_id) filter (where se.superseded_at is null) as scored_matches,
  coalesce(sum(se.points) filter (where se.superseded_at is null), 0)::numeric(12,2)
    as points,
  coalesce(sum(se.points) filter (
    where se.superseded_at is null and se.event_type = 'upset'
  ), 0)::numeric(12,2) as upset_points
from public.scoring_events se
join public.leagues l on l.id = se.league_id
join public.teams t on t.id = se.team_id
group by l.public_id, t.public_id, t.name;

create or replace view public.v_member_scoring_analytics
with (security_invoker = true)
as
with event_totals as (
  select
    current_league_member_id as league_member_id,
    count(distinct match_id) filter (where superseded_at is null) as scored_matches,
    coalesce(sum(points) filter (where superseded_at is null), 0)::numeric(12,2)
      as event_points,
    coalesce(sum(points) filter (
      where superseded_at is null and event_type = 'upset'
    ), 0)::numeric(12,2) as upset_points
  from public.v_scoring_events_current_owner
  where current_league_member_id is not null
  group by current_league_member_id
),
bonus_totals as (
  select
    current_league_member_id as league_member_id,
    coalesce(sum(points) filter (where revoked_at is null), 0)::numeric(12,2)
      as bonus_points
  from public.v_bonuses_current_owner
  where current_league_member_id is not null
  group by current_league_member_id
)
select
  l.public_id as league_public_id,
  lm.public_id as member_public_id,
  p.display_name,
  coalesce(et.scored_matches, 0) as scored_matches,
  coalesce(et.event_points, 0) + coalesce(bt.bonus_points, 0) as total_points,
  coalesce(et.upset_points, 0) as upset_points
from public.league_members lm
join public.leagues l on l.id = lm.league_id
join public.profiles p on p.id = lm.profile_id
left join event_totals et on et.league_member_id = lm.id
left join bonus_totals bt on bt.league_member_id = lm.id;

grant select on public.v_scoring_events_current_owner,
  public.v_bonuses_current_owner to authenticated;

commit;
