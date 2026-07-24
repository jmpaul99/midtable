begin;

alter table public.competition_templates
  add column if not exists payout_config jsonb not null default '[]'::jsonb,
  add constraint competition_templates_payout_config_array
    check (jsonb_typeof(payout_config) = 'array');

alter table public.competitions
  add column if not exists provider_params jsonb not null default '{}'::jsonb;

alter table public.pools
  add column if not exists provider_competition_code text,
  add column if not exists scoring_enabled boolean not null default true;

alter table public.table_snapshots
  add column if not exists pool_id bigint references public.pools(id) on delete cascade;
alter table public.table_snapshots
  drop constraint if exists table_snapshots_competition_id_kickoff_at_source_match_version_key;
do $$
declare
  constraint_name text;
begin
  select c.conname into constraint_name
  from pg_constraint c
  where c.conrelid = 'public.table_snapshots'::regclass
    and c.contype = 'u'
    and pg_get_constraintdef(c.oid) ilike
      '%(competition_id, kickoff_at, source_match_version)%'
  limit 1;
  if constraint_name is not null then
    execute format(
      'alter table public.table_snapshots drop constraint %I',
      constraint_name
    );
  end if;
end;
$$;
drop index if exists public.table_snapshots_competition_kickoff_version_key;
create unique index if not exists table_snapshots_pool_kickoff_version_key
  on public.table_snapshots (pool_id, kickoff_at, source_match_version)
  where pool_id is not null;

alter table public.rankings
  add column if not exists phase text not null default 'overall';
alter table public.rankings drop constraint if exists rankings_league_id_as_of_kickoff_at_league_member_id_key;
create unique index if not exists rankings_league_phase_kickoff_member_key
  on public.rankings (league_id, phase, as_of_kickoff_at, league_member_id);

alter table public.draft_states
  add column if not exists draft_format text not null default 'linear',
  add constraint draft_states_draft_format_check
    check (draft_format in ('linear', 'snake'));

alter table public.roster_entries
  drop constraint if exists roster_entries_acquired_via_check;
alter table public.roster_entries
  add constraint roster_entries_acquired_via_check
  check (acquired_via in ('draft', 'keeper', 'preassigned', 'trade', 'waiver', 'admin'));

create table public.ranking_lists (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  league_id bigint not null references public.leagues(id) on delete cascade,
  pool_id bigint not null references public.pools(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 160),
  status text not null default 'draft' check (status in ('draft', 'locked')),
  locked_at timestamptz,
  locked_by_profile_id bigint references public.profiles(id),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (league_id, pool_id, name),
  check ((status = 'locked') = (locked_at is not null))
);

create table public.ranking_list_rows (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  ranking_list_id bigint not null references public.ranking_lists(id) on delete cascade,
  league_member_id bigint not null references public.league_members(id) on delete cascade,
  pool_team_id bigint not null references public.pool_teams(id) on delete cascade,
  rank integer not null check (rank > 0),
  source_value text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  unique (ranking_list_id, league_member_id, pool_team_id),
  unique (ranking_list_id, league_member_id, rank)
);

create table public.audit_events (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid() unique,
  league_id bigint not null references public.leagues(id) on delete cascade,
  actor_profile_id bigint references public.profiles(id),
  action text not null,
  entity_type text not null,
  entity_public_id uuid,
  before_data jsonb,
  after_data jsonb,
  reason text,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists audit_events_league_created_idx
  on public.audit_events (league_id, created_at desc);
create index if not exists ranking_list_rows_member_idx
  on public.ranking_list_rows (league_member_id, rank);

create trigger ranking_lists_set_updated_at before update on public.ranking_lists
  for each row execute function public.set_updated_at();
create trigger ranking_list_rows_set_updated_at before update on public.ranking_list_rows
  for each row execute function public.set_updated_at();

alter table public.ranking_lists enable row level security;
alter table public.ranking_list_rows enable row level security;
alter table public.audit_events enable row level security;

create policy ranking_lists_read_members on public.ranking_lists
  for select to authenticated using (public.is_league_member(league_id));
create policy ranking_list_rows_read_members on public.ranking_list_rows
  for select to authenticated using (
    exists (
      select 1 from public.ranking_lists rl
      where rl.id = ranking_list_rows.ranking_list_id
        and public.is_league_member(rl.league_id)
    )
  );
create policy audit_events_read_commissioners on public.audit_events
  for select to authenticated using (public.is_league_commissioner(league_id));

grant select on public.ranking_lists, public.ranking_list_rows,
  public.audit_events to authenticated;

commit;
