begin;

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table public.competition_templates (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  code text not null unique check (code ~ '^[A-Z0-9_-]+$'),
  name text not null,
  provider text not null default 'football-data.org',
  provider_competition_code text not null,
  default_team_count integer not null check (default_team_count > 1),
  default_roster_size integer not null check (default_roster_size > 0),
  pool_definitions jsonb not null default '[]'::jsonb,
  scoring_config jsonb not null default '{}'::jsonb,
  tiebreak_config jsonb not null default '["total_points","upset_points","win_count"]'::jsonb,
  draft_config jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  check (jsonb_typeof(pool_definitions) = 'array'),
  check (jsonb_typeof(scoring_config) = 'object'),
  check (jsonb_typeof(tiebreak_config) = 'array'),
  check (jsonb_typeof(draft_config) = 'object')
);

create table public.profiles (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  auth_user_id uuid not null unique references auth.users(id) on delete cascade,
  display_name text not null check (length(trim(display_name)) between 1 and 80),
  avatar_url text,
  timezone text not null default 'UTC',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table public.competitions (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  template_id bigint not null references public.competition_templates(id),
  season text not null,
  provider_competition_id text,
  starts_at timestamptz,
  ends_at timestamptz,
  status text not null default 'scheduled'
    check (status in ('scheduled', 'active', 'completed', 'archived')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (template_id, season),
  check (ends_at is null or starts_at is null or ends_at > starts_at)
);

create table public.leagues (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  competition_id bigint not null references public.competitions(id),
  owner_profile_id bigint not null references public.profiles(id),
  name text not null check (length(trim(name)) between 1 and 160),
  slug text not null unique check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  status text not null default 'setup'
    check (status in ('setup', 'drafting', 'active', 'completed', 'archived')),
  visibility text not null default 'private'
    check (visibility in ('private', 'unlisted', 'public')),
  max_members integer not null check (max_members between 2 and 100),
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table public.league_members (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  league_id bigint not null references public.leagues(id) on delete cascade,
  profile_id bigint not null references public.profiles(id) on delete cascade,
  role text not null default 'member' check (role in ('owner', 'commissioner', 'member')),
  status text not null default 'active' check (status in ('active', 'left', 'removed')),
  joined_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (league_id, profile_id)
);

create table public.invites (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  league_id bigint not null references public.leagues(id) on delete cascade,
  invited_by_member_id bigint not null references public.league_members(id),
  email text,
  token_hash text not null unique,
  role text not null default 'member' check (role in ('commissioner', 'member')),
  status text not null default 'pending'
    check (status in ('pending', 'accepted', 'revoked', 'expired')),
  expires_at timestamptz not null,
  accepted_by_profile_id bigint references public.profiles(id),
  accepted_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  check ((status = 'accepted') = (accepted_at is not null)),
  check (accepted_at is null or accepted_by_profile_id is not null)
);

create table public.pools (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  league_id bigint not null references public.leagues(id) on delete cascade,
  definition_key text not null check (definition_key ~ '^[a-z0-9_]+$'),
  name text not null check (length(trim(name)) between 1 and 120),
  ordinal integer not null check (ordinal > 0),
  roster_size integer not null check (roster_size > 0),
  draft_order jsonb not null default '[]'::jsonb check (jsonb_typeof(draft_order) = 'array'),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (league_id, ordinal),
  unique (league_id, definition_key),
  unique (league_id, name)
);

create table public.teams (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  competition_id bigint not null references public.competitions(id) on delete cascade,
  provider_team_id text not null,
  name text not null,
  short_name text,
  tla text,
  crest_url text,
  venue text,
  is_active boolean not null default true,
  provider_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (competition_id, provider_team_id),
  unique (competition_id, name)
);

create table public.pool_teams (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  pool_id bigint not null references public.pools(id) on delete cascade,
  team_id bigint not null references public.teams(id) on delete cascade,
  seed integer check (seed > 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (pool_id, team_id),
  unique (pool_id, seed)
);

create table public.roster_slots (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  pool_id bigint not null references public.pools(id) on delete cascade,
  league_member_id bigint not null references public.league_members(id) on delete cascade,
  slot_number integer not null check (slot_number > 0),
  label text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (pool_id, league_member_id, slot_number)
);

create table public.roster_entries (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  roster_slot_id bigint not null references public.roster_slots(id) on delete cascade,
  pool_team_id bigint not null references public.pool_teams(id),
  acquired_via text not null default 'draft' check (acquired_via in ('draft', 'trade', 'waiver', 'admin')),
  valid_from timestamptz not null default timezone('utc', now()),
  valid_until timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  check (valid_until is null or valid_until > valid_from)
);

create unique index roster_entries_one_current_per_slot
  on public.roster_entries (roster_slot_id) where valid_until is null;
create unique index roster_entries_one_current_owner_per_team
  on public.roster_entries (pool_team_id) where valid_until is null;

create table public.draft_states (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  pool_id bigint not null unique references public.pools(id) on delete cascade,
  status text not null default 'pending'
    check (status in ('pending', 'running', 'paused', 'completed', 'cancelled')),
  current_pick_number integer not null default 1 check (current_pick_number > 0),
  current_round integer not null default 1 check (current_round > 0),
  current_member_id bigint references public.league_members(id),
  pick_deadline_at timestamptz,
  version integer not null default 1 check (version > 0),
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table public.draft_picks (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  draft_state_id bigint not null references public.draft_states(id) on delete cascade,
  pool_id bigint not null references public.pools(id) on delete cascade,
  pick_number integer not null check (pick_number > 0),
  round_number integer not null check (round_number > 0),
  round_pick_number integer not null check (round_pick_number > 0),
  league_member_id bigint not null references public.league_members(id),
  pool_team_id bigint not null references public.pool_teams(id),
  roster_slot_id bigint not null references public.roster_slots(id),
  idempotency_key uuid not null default gen_random_uuid(),
  picked_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (draft_state_id, pick_number),
  unique (draft_state_id, round_number, round_pick_number),
  unique (draft_state_id, pool_team_id),
  unique (draft_state_id, roster_slot_id),
  unique (draft_state_id, idempotency_key)
);

create table public.matches (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  competition_id bigint not null references public.competitions(id) on delete cascade,
  provider_match_id text not null,
  matchday integer check (matchday > 0),
  stage text,
  home_team_id bigint not null references public.teams(id),
  away_team_id bigint not null references public.teams(id),
  kickoff_at timestamptz not null,
  status text not null
    check (status in ('scheduled', 'timed', 'in_play', 'paused', 'finished', 'postponed', 'suspended', 'cancelled')),
  home_score integer check (home_score >= 0),
  away_score integer check (away_score >= 0),
  winner text check (winner in ('home', 'away', 'draw')),
  duration text,
  result_version integer not null default 1 check (result_version > 0),
  provider_updated_at timestamptz,
  provider_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (competition_id, provider_match_id),
  check (home_team_id <> away_team_id),
  check ((status = 'finished') = (home_score is not null and away_score is not null and winner is not null))
);

create index matches_competition_kickoff_idx
  on public.matches (competition_id, kickoff_at, id);

create table public.table_snapshots (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  competition_id bigint not null references public.competitions(id) on delete cascade,
  kickoff_at timestamptz not null,
  source_match_version integer not null default 1 check (source_match_version > 0),
  computed_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (competition_id, kickoff_at, source_match_version)
);

create table public.table_snapshot_rows (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  snapshot_id bigint not null references public.table_snapshots(id) on delete cascade,
  team_id bigint not null references public.teams(id) on delete cascade,
  position integer not null check (position > 0),
  played integer not null default 0 check (played >= 0),
  won integer not null default 0 check (won >= 0),
  drawn integer not null default 0 check (drawn >= 0),
  lost integer not null default 0 check (lost >= 0),
  goals_for integer not null default 0 check (goals_for >= 0),
  goals_against integer not null default 0 check (goals_against >= 0),
  goal_difference integer generated always as (goals_for - goals_against) stored,
  points integer not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (snapshot_id, team_id),
  unique (snapshot_id, position),
  check (played = won + drawn + lost)
);

create table public.rankings (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  league_id bigint not null references public.leagues(id) on delete cascade,
  league_member_id bigint not null references public.league_members(id) on delete cascade,
  as_of_kickoff_at timestamptz not null,
  rank integer not null check (rank > 0),
  total_points numeric(12,2) not null default 0,
  win_count integer not null default 0 check (win_count >= 0),
  upset_points numeric(12,2) not null default 0,
  goals_for integer not null default 0 check (goals_for >= 0),
  tiebreak_values jsonb not null default '{}'::jsonb,
  computed_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (league_id, as_of_kickoff_at, league_member_id)
);

create table public.scoring_events (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  league_id bigint not null references public.leagues(id) on delete cascade,
  match_id bigint not null references public.matches(id) on delete cascade,
  team_id bigint not null references public.teams(id),
  roster_entry_id bigint references public.roster_entries(id) on delete set null,
  league_member_id bigint not null references public.league_members(id),
  snapshot_id bigint not null references public.table_snapshots(id),
  phase text not null,
  event_type text not null check (event_type in ('result', 'upset', 'adjustment')),
  points numeric(10,2) not null,
  source_result_version integer not null check (source_result_version > 0),
  details jsonb not null default '{}'::jsonb,
  superseded_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create unique index scoring_events_active_natural_key
  on public.scoring_events
  (league_id, match_id, team_id, league_member_id, phase, event_type)
  where superseded_at is null;
create index scoring_events_team_idx on public.scoring_events (team_id, match_id);

create table public.bonuses (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  league_id bigint not null references public.leagues(id) on delete cascade,
  league_member_id bigint not null references public.league_members(id),
  team_id bigint references public.teams(id),
  match_id bigint references public.matches(id),
  bonus_type text not null,
  points numeric(10,2) not null,
  reason text not null,
  awarded_by_profile_id bigint references public.profiles(id),
  awarded_at timestamptz not null default timezone('utc', now()),
  revoked_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  check (revoked_at is null or revoked_at >= awarded_at)
);

create table public.sync_status (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  competition_id bigint not null references public.competitions(id) on delete cascade,
  resource_type text not null check (resource_type in ('competition', 'teams', 'matches', 'standings')),
  cursor_value text,
  status text not null default 'idle' check (status in ('idle', 'running', 'succeeded', 'failed', 'rate_limited')),
  last_attempt_at timestamptz,
  last_success_at timestamptz,
  next_attempt_at timestamptz,
  rate_limit_remaining integer check (rate_limit_remaining >= 0),
  rate_limit_reset_at timestamptz,
  last_error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (competition_id, resource_type)
);

create index league_members_profile_idx on public.league_members (profile_id);
create index roster_entries_team_history_idx
  on public.roster_entries (pool_team_id, valid_from, valid_until);
create index rankings_latest_idx on public.rankings (league_id, as_of_kickoff_at desc);
create index rankings_rank_idx
  on public.rankings (league_id, as_of_kickoff_at, rank);
create index sync_status_due_idx on public.sync_status (status, next_attempt_at);

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'competition_templates', 'profiles', 'competitions', 'leagues', 'league_members',
    'invites', 'pools', 'teams', 'pool_teams', 'roster_slots', 'roster_entries',
    'draft_states', 'draft_picks', 'matches', 'table_snapshots',
    'table_snapshot_rows', 'rankings', 'scoring_events', 'bonuses', 'sync_status'
  ]
  loop
    execute format(
      'create trigger %I_set_updated_at before update on public.%I '
      'for each row execute function public.set_updated_at()',
      table_name, table_name
    );
  end loop;
end;
$$;

create view public.v_league_standings
with (security_invoker = true)
as
select distinct on (r.league_id, r.league_member_id)
  l.public_id as league_public_id,
  lm.public_id as member_public_id,
  p.display_name,
  r.rank,
  r.total_points,
  r.win_count,
  r.upset_points,
  r.goals_for,
  r.as_of_kickoff_at
from public.rankings r
join public.leagues l on l.id = r.league_id
join public.league_members lm on lm.id = r.league_member_id
join public.profiles p on p.id = lm.profile_id
order by r.league_id, r.league_member_id, r.as_of_kickoff_at desc;

create view public.v_team_scoring_analytics
with (security_invoker = true)
as
select
  l.public_id as league_public_id,
  t.public_id as team_public_id,
  t.name as team_name,
  count(distinct se.match_id) filter (where se.superseded_at is null) as scored_matches,
  coalesce(sum(se.points) filter (where se.superseded_at is null), 0)::numeric(12,2) as points,
  coalesce(sum(se.points) filter (
    where se.superseded_at is null and se.event_type = 'upset'
  ), 0)::numeric(12,2) as upset_points
from public.scoring_events se
join public.leagues l on l.id = se.league_id
join public.teams t on t.id = se.team_id
group by l.public_id, t.public_id, t.name;

create view public.v_member_scoring_analytics
with (security_invoker = true)
as
with event_totals as (
  select
    league_member_id,
    count(distinct match_id) filter (where superseded_at is null) as scored_matches,
    coalesce(sum(points) filter (where superseded_at is null), 0)::numeric(12,2)
      as event_points,
    coalesce(sum(points) filter (
      where superseded_at is null and event_type = 'upset'
    ), 0)::numeric(12,2) as upset_points
  from public.scoring_events
  group by league_member_id
),
bonus_totals as (
  select
    league_member_id,
    coalesce(sum(points) filter (where revoked_at is null), 0)::numeric(12,2)
      as bonus_points
  from public.bonuses
  group by league_member_id
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

alter table public.profiles enable row level security;
alter table public.leagues enable row level security;
alter table public.league_members enable row level security;
alter table public.invites enable row level security;
alter table public.pools enable row level security;
alter table public.roster_slots enable row level security;
alter table public.roster_entries enable row level security;
alter table public.draft_states enable row level security;
alter table public.draft_picks enable row level security;
alter table public.rankings enable row level security;
alter table public.scoring_events enable row level security;
alter table public.bonuses enable row level security;

create policy profiles_update_self on public.profiles
  for update to authenticated
  using (auth.uid() = auth_user_id)
  with check (auth.uid() = auth_user_id);

create or replace function public.is_league_member(target_league_id bigint)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.league_members lm
    join public.profiles p on p.id = lm.profile_id
    where lm.league_id = target_league_id
      and lm.status = 'active'
      and p.auth_user_id = auth.uid()
  );
$$;

create or replace function public.can_view_profile(target_profile_id bigint)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.profiles target
    where target.id = target_profile_id
      and (
        target.auth_user_id = auth.uid()
        or exists (
          select 1
          from public.league_members target_member
          join public.league_members viewer_member
            on viewer_member.league_id = target_member.league_id
            and viewer_member.status = 'active'
          join public.profiles viewer on viewer.id = viewer_member.profile_id
          where target_member.profile_id = target.id
            and target_member.status = 'active'
            and viewer.auth_user_id = auth.uid()
        )
      )
  );
$$;

create or replace function public.is_league_commissioner(target_league_id bigint)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.league_members lm
    join public.profiles p on p.id = lm.profile_id
    where lm.league_id = target_league_id
      and lm.status = 'active'
      and lm.role in ('owner', 'commissioner')
      and p.auth_user_id = auth.uid()
  );
$$;

create policy profiles_read_self_or_league_members on public.profiles
  for select to authenticated using (public.can_view_profile(id));
create policy leagues_read_members_or_public on public.leagues
  for select to authenticated
  using (visibility = 'public' or public.is_league_member(id));
create policy league_members_read_members on public.league_members
  for select to authenticated using (public.is_league_member(league_id));
create policy invites_read_commissioners on public.invites
  for select to authenticated using (public.is_league_commissioner(league_id));
create policy pools_read_members on public.pools
  for select to authenticated using (public.is_league_member(league_id));
create policy rankings_read_members on public.rankings
  for select to authenticated using (public.is_league_member(league_id));
create policy scoring_events_read_members on public.scoring_events
  for select to authenticated using (public.is_league_member(league_id));
create policy bonuses_read_members on public.bonuses
  for select to authenticated using (public.is_league_member(league_id));
create policy roster_slots_read_members on public.roster_slots
  for select to authenticated using (
    exists (
      select 1 from public.pools p
      where p.id = roster_slots.pool_id and public.is_league_member(p.league_id)
    )
  );
create policy roster_entries_read_members on public.roster_entries
  for select to authenticated using (
    exists (
      select 1
      from public.roster_slots rs
      join public.pools p on p.id = rs.pool_id
      where rs.id = roster_entries.roster_slot_id
        and public.is_league_member(p.league_id)
    )
  );
create policy draft_states_read_members on public.draft_states
  for select to authenticated using (
    exists (
      select 1 from public.pools p
      where p.id = draft_states.pool_id and public.is_league_member(p.league_id)
    )
  );
create policy draft_picks_read_members on public.draft_picks
  for select to authenticated using (
    exists (
      select 1 from public.pools p
      where p.id = draft_picks.pool_id and public.is_league_member(p.league_id)
    )
  );

grant select on public.competition_templates, public.competitions, public.teams,
  public.pool_teams, public.matches, public.table_snapshots,
  public.table_snapshot_rows to authenticated;
grant select on public.profiles, public.leagues, public.league_members,
  public.invites, public.pools, public.roster_slots, public.roster_entries,
  public.draft_states, public.draft_picks, public.rankings,
  public.scoring_events, public.bonuses to authenticated;
grant select on public.v_league_standings, public.v_team_scoring_analytics,
  public.v_member_scoring_analytics to authenticated;

commit;
