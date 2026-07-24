begin;

alter table public.scoring_events
  drop constraint if exists scoring_events_event_type_check;

alter table public.bonuses
  add column if not exists phase text not null default 'overall'
    check (length(trim(phase)) between 1 and 80);

create index if not exists bonuses_league_phase_type_idx
  on public.bonuses (league_id, phase, bonus_type)
  where revoked_at is null;

update public.competition_templates
set
  scoring_config = jsonb_set(
    scoring_config,
    '{upset,thresholds}',
    '[
      {
        "key": "minor_upset",
        "result": "win",
        "minimum_position_gap": 5,
        "maximum_position_gap": 9,
        "bonus": 1
      },
      {
        "key": "major_upset",
        "result": "win",
        "minimum_position_gap": 10,
        "maximum_position_gap": null,
        "bonus": 3
      },
      {
        "key": "major_upset_draw",
        "result": "draw",
        "minimum_position_gap": 10,
        "maximum_position_gap": null,
        "bonus": 1
      }
    ]'::jsonb,
    true
  ),
  tiebreak_config = '[
    {
      "metric": "total_points",
      "direction": "desc"
    },
    {
      "metric": "event_points",
      "event_types": ["minor_upset", "major_upset", "major_upset_draw"],
      "direction": "desc"
    },
    {
      "metric": "event_count",
      "event_types": ["win"],
      "direction": "desc"
    }
  ]'::jsonb,
  updated_at = timezone('utc', now())
where code = 'PL';

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
    where se.superseded_at is null and se.event_type not in ('win', 'draw', 'loss')
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
      where superseded_at is null and event_type not in ('win', 'draw', 'loss')
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

commit;
