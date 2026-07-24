export type UUID = string;
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export interface LeagueSummary {
  id: UUID;
  name: string;
  slug: string;
  status: string;
  visibility: string;
  max_members: number;
  role: string;
  season: string;
  template_id: UUID;
}

export interface Member {
  id: UUID;
  profile_id: UUID;
  display_name: string;
  role: string;
  status: string;
  joined_at: string;
}

export interface Pool {
  id: UUID;
  definition_key: string;
  name: string;
  ordinal: number;
  roster_size: number;
  draft_order: UUID[] | null;
  provider_competition_code: string;
  scoring_enabled: boolean;
  provider_params: Record<string, Json>;
}

export interface PhaseMetadata {
  key: string;
  name: string;
  matchweek_range: number[] | null;
  stage_in: string[] | null;
  matching_matches: number;
  finished_matches: number;
  remaining_matches: number;
  is_final: boolean;
}

export interface League extends LeagueSummary {
  current_member_id: UUID;
  settings: Record<string, Json>;
  pools: Pool[];
  members: Member[];
  phases: PhaseMetadata[];
  bonus_type_keys: string[];
  provider_params: Record<string, Json>;
  created_at: string;
}

export interface PoolConfig {
  key: string;
  name: string;
  provider_competition_code: string;
  slots_per_member: number;
  slot_label: string;
  scoring_enabled: boolean;
}

export interface LeaderboardRung {
  metric: "total_points" | "event_points" | "event_count" | "bonus_points" | "bonus_count";
  event_types?: string[];
  bonus_type_keys?: string[];
  direction: "desc" | "asc";
}

export interface CompetitionTemplate {
  id: UUID;
  code: string;
  name: string;
  provider: string;
  provider_competition_code: string;
  default_team_count: number;
  default_roster_size: number;
  pools: PoolConfig[];
  scoring: Record<string, Json>;
  phases: Record<string, Json>[];
  leaderboard_tiebreaks: LeaderboardRung[];
  bonuses: Record<string, number>;
  payouts: Record<string, Json>[];
  draft: Record<string, Json>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type TemplateWrite = Omit<CompetitionTemplate, "id" | "created_at" | "updated_at">;

export interface Standing {
  member_id: UUID;
  display_name: string;
  rank: number;
  total_points: number | string;
  upset_points: number | string;
  win_count: number;
  payout: number | string;
  metric_values: Array<LeaderboardRung & { value: number | string }>;
}

export interface StandingsResponse {
  phase: PhaseMetadata;
  entries: Standing[];
}

export interface PoolTeam {
  id: UUID;
  name: string;
  crest_url: string | null;
  provider_team_id: string;
  drafted: boolean;
  current_owner: { member_id: UUID; display_name: string; acquired_via: string } | null;
  available: boolean;
}

export interface DraftPick {
  id?: UUID;
  pick_number?: number;
  round_number?: number;
  member_id?: UUID;
  team_id?: UUID;
  team_name?: string;
  [key: string]: unknown;
}

export interface DraftState {
  id: UUID;
  pool_id: UUID;
  status: string;
  current_pick_number: number;
  current_round: number;
  current_member_id: UUID | null;
  version: number;
  picks: DraftPick[];
}

export interface RosterRow {
  member_id: UUID;
  display_name: string;
  pool_id: UUID;
  pool_name: string;
  slot_number: number;
  team_id: UUID | null;
  team_name: string | null;
  acquired_via: string | null;
  valid_from: string | null;
  valid_until: string | null;
}

export interface Invite {
  id: UUID;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  token: string | null;
}

export interface Bonus {
  id: UUID;
  member_id: UUID | null;
  display_name: string | null;
  team_id: UUID;
  match_id: UUID | null;
  bonus_type: string;
  phase: string;
  points: number | string;
  reason: string;
  awarded_at: string;
  revoked_at: string | null;
}

export interface RankingList {
  id: UUID;
  pool_id: UUID;
  name: string;
  status: string;
  locked_at: string | null;
  rows: Array<{
    id: UUID;
    member_id: UUID;
    team_id: UUID;
    name: string;
    rank: number;
    source_value: string;
  }>;
}

export interface SyncStatus {
  id: UUID;
  resource_type: string;
  status: string;
  last_attempt_at: string | null;
  last_success_at: string | null;
  next_attempt_at: string | null;
  rate_limit_remaining: number | null;
  rate_limit_reset_at: string | null;
  last_error: string | null;
}

export interface Readiness {
  ready: boolean;
  errors: string[];
  warnings: string[];
}

export interface MatchEvent {
  id: UUID;
  match_id: UUID;
  kickoff_at: string;
  matchday: number;
  team_id: UUID;
  team_name: string;
  member_id: UUID | null;
  display_name: string | null;
  phase: string;
  event_type: string;
  points: number | string;
  details: Record<string, Json>;
  source_result_version: number;
}

export interface Snapshot {
  id: UUID;
  pool_id: UUID;
  kickoff_at: string;
  source_match_version: number;
  computed_at: string;
  rows: Array<{
    team_id: UUID;
    team_name: string;
    position: number;
    played: number;
    points: number;
  }>;
}

export type AnalyticsRow = Record<string, string | number | null | Record<string, Json>>;

export interface Message {
  detail: string;
}
