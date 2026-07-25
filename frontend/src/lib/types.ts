export type UUID = string;
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export interface Me {
  id: UUID;
  email: string;
  display_name: string;
  auth_user_id: UUID | null;
  is_platform_admin?: boolean;
}

export interface LeagueSummary {
  id: UUID;
  name: string;
  season_label: string;
  status: string;
  draft_style: string;
  template_id?: UUID | null;
  /** @deprecated use season_label */
  season?: string;
  role?: string;
  visibility?: string;
  max_members?: number | null;
  /** Post-draft roster club order preference. Pre-draft always uses competition order. */
  roster_club_order?: "draft" | "competition";
  slug?: string;
  my_rank?: number | null;
  member_count?: number | null;
  my_points?: number | null;
  my_draft_slot?: number | null;
  has_scored?: boolean;
}

export interface Manager {
  id: UUID;
  profile_id: UUID | null;
  display_name: string | null;
  team_name?: string | null;
  email?: string | null;
  role: string;
  is_commissioner: boolean;
  draft_slot: number | null;
  status?: string;
  joined_at?: string;
}

/** @deprecated Use Manager */
export type Member = Manager;

/** Fantasy team name, then profile display name, then email / fallback. */
export function managerLabel(
  m: Pick<Manager, "team_name" | "display_name" | "email"> | null | undefined,
  fallback = "Manager",
): string {
  if (!m) return fallback;
  return m.team_name?.trim() || m.display_name?.trim() || m.email || fallback;
}

/** @deprecated Use managerLabel */
export const memberLabel = managerLabel;

export interface Pool {
  id: UUID;
  key: string;
  label: string;
  scores_match_results: boolean;
  slot_count: number;
  sort_order?: number;
  provider: string;
  competition_code: string | null;
  season_year: number | null;
  /** FE aliases */
  name?: string;
  definition_key?: string;
  roster_size?: number;
  scoring_enabled?: boolean;
}

export interface PhaseMetadata {
  key: string;
  name: string;
  matchweek_range: number[] | null;
  stage_in: string[] | null;
  matching_matches?: number;
  finished_matches?: number;
  remaining_matches?: number;
  is_final: boolean;
  include_bonus_types?: string[];
}

export interface League extends LeagueSummary {
  current_member_id: UUID | null;
  role: string;
  settings: Record<string, Json>;
  pools: Pool[];
  members: Member[];
  phases: PhaseMetadata[];
  bonus_type_keys: string[];
  provider_params: Record<string, Json>;
  result_points?: Record<string, Json>;
  upset_rules?: Record<string, Json>;
  leaderboard_phases?: Record<string, Json>[];
  leaderboard_tiebreaks?: LeaderboardRung[];
  buy_in?: number | string;
  payouts?: Json[];
  preassign_mode?: string;
  season: string;
  max_members?: number | null;
  roster_club_order?: "draft" | "competition";
  visibility: string;
}

export interface LeaderboardRung {
  metric: "total_points" | "event_points" | "event_count" | "bonus_points" | "bonus_count" | string;
  event_types?: string[];
  bonus_type_keys?: string[];
  direction?: "desc" | "asc";
  value?: number | string;
}

export interface CompetitionTemplate {
  id: UUID;
  key: string;
  label: string;
  draft_style: string;
  preassign_mode: string;
  result_points: Record<string, Json>;
  upset_rules: Record<string, Json>;
  leaderboard_phases: Record<string, Json>[];
  leaderboard_tiebreaks: LeaderboardRung[];
  buy_in: number | string;
  payouts: Json[];
  roster_slots: Json[];
  pool_definitions: Json[];
  bonus_types: Json[];
  /** legacy aliases used by older UI */
  code?: string;
  name?: string;
  is_active?: boolean;
  pools?: Json[];
  scoring?: Record<string, Json>;
  phases?: Record<string, Json>[];
  bonuses?: Record<string, number>;
  draft?: Record<string, Json>;
  created_at?: string;
  updated_at?: string;
}

export type TemplateWrite = {
  key: string;
  label: string;
  draft_style: string;
  preassign_mode: string;
  result_points: Record<string, Json>;
  upset_rules: Record<string, Json>;
  leaderboard_phases: Record<string, Json>[];
  leaderboard_tiebreaks: LeaderboardRung[];
  buy_in: number | string;
  payouts: Json[];
  roster_slots: Json[];
  pool_definitions: Json[];
  bonus_types: Json[];
};

export interface Standing {
  member_id: UUID;
  display_name: string;
  team_name?: string | null;
  owner_name?: string | null;
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
  crest_url?: string | null;
  pool_id?: UUID;
}

export interface DraftState {
  id: UUID;
  status: string;
  current_pick_number: number;
  current_round: number;
  current_member_id: UUID | null;
  on_clock_member_id?: UUID | null;
  version: number;
  picks: DraftPick[];
  league_status?: string;
}

export interface RosterRow {
  id?: UUID | null;
  member_id: UUID;
  display_name: string;
  pool_id: UUID;
  pool_name: string;
  pool_sort_order?: number;
  slot_number: number;
  team_id: UUID | null;
  team_name: string | null;
  crest_url?: string | null;
  acquired_via: string | null;
  draft_pick_number?: number | null;
  points?: number | null;
  games_played?: number | null;
  points_per_game?: number | null;
  form?: string[] | null;
  rank?: number | null;
  member_total_points?: number | null;
  member_points_per_game?: number | null;
  member_wins?: number | null;
  member_draws?: number | null;
  member_losses?: number | null;
  member_games_played?: number | null;
  points_by_stage?: Record<string, number>;
}

export interface InviteEmailDelivery {
  id: UUID;
  status: "sent" | "failed" | "skipped" | string;
  trigger: "create" | "resend" | string;
  error?: string | null;
  provider_message_id?: string | null;
  http_attempts: number;
  created_at: string;
}

export interface Invite {
  id: UUID;
  email: string;
  role: string;
  status: string;
  is_commissioner?: boolean;
  draft_slot?: number | null;
  expires_at?: string;
  token: string | null;
  accept_url?: string | null;
  email_sent?: boolean | null;
  email_error?: string | null;
  email_deliveries?: InviteEmailDelivery[];
}

export interface JoinLink {
  enabled: boolean;
  token: string | null;
  join_url: string | null;
}

export interface Bonus {
  id: UUID;
  member_id: UUID | null;
  display_name: string | null;
  team_id: UUID;
  match_id?: UUID | null;
  bonus_type: string;
  phase?: string;
  points: number | string;
  reason: string | null;
  awarded_at: string | null;
  revoked_at: string | null;
}

export interface RankingList {
  id: UUID;
  key: string;
  label: string;
  source: string;
  locked: boolean;
  as_of?: string | null;
}

export interface SyncStatus {
  id: UUID;
  provider?: string;
  resource_type?: string;
  status: string;
  last_attempt_at: string | null;
  last_success_at: string | null;
  next_attempt_at?: string | null;
  rate_limit_remaining: number | null;
  rate_limit_reset_at?: string | null;
  last_error: string | null;
  in_progress?: boolean;
}

export interface ReadinessCheck {
  key: string;
  label: string;
  status: "ok" | "error" | "warning" | string;
  detail?: string | null;
}

export interface Readiness {
  ready: boolean;
  checks?: ReadinessCheck[];
  errors: string[];
  warnings: string[];
}

/** GET /leagues/{id}/match-log row (fixtures, not scoring events). */
export interface MatchLogRow {
  id: UUID;
  kickoff_at: string;
  status: string;
  scheduled_matchweek: number | null;
  home_team_id: UUID;
  away_team_id: UUID;
  home_team_name: string;
  away_team_name: string;
  home_goals: number | null;
  away_goals: number | null;
  pool_id: UUID;
  home_points?: number | null;
  away_points?: number | null;
}

export interface TeamFixture extends MatchLogRow {
  is_home: boolean;
  points: number | null;
  opponent_name: string;
  opponent_id: UUID;
  opponent_table_position?: number | null;
}

export interface VenueSplit {
  wins: number;
  draws: number;
  losses: number;
  games_played: number;
  points: number;
  points_per_game: number;
}

export interface BonusAward {
  id: UUID;
  team_id: UUID | null;
  team_name: string | null;
  crest_url?: string | null;
  bonus_type: string;
  bonus_type_label: string;
  points: number;
  reason: string | null;
  awarded_at: string | null;
}

export interface ScoringEventMatch {
  id: UUID;
  event_type: string;
  points: number;
  match_id: UUID;
  kickoff_at: string;
  scheduled_matchweek: number | null;
  status: string;
  is_home: boolean;
  home_goals: number | null;
  away_goals: number | null;
  opponent_id: UUID;
  opponent_name: string;
  metadata?: Record<string, Json>;
}

export interface TeamDetail {
  id: UUID;
  name: string;
  crest_url: string | null;
  pool_id: UUID | null;
  pool_name: string | null;
  owner: { member_id: UUID | null; display_name: string | null; acquired_via: string } | null;
  stats: {
    total_points: number;
    games_played: number;
    wins: number;
    draws: number;
    losses: number;
    upset_points: number;
    bonus_points: number;
    points_per_game: number;
    event_points_by_type?: Record<string, number>;
    event_counts_by_type?: Record<string, number>;
    bonus_points_by_type?: Record<string, number>;
    points_by_stage?: Record<string, number>;
    goals_for?: number;
    goals_against?: number;
    goal_difference?: number;
    table_position?: number | null;
    table_points?: number | null;
    form?: string[];
    current_streak?: { result: string; count: number } | null;
    home?: VenueSplit;
    away?: VenueSplit;
    upcoming_difficulty?: {
      next_three: Array<{
        match_id: string;
        opponent_name: string;
        opponent_id: string;
        opponent_table_position: number | null;
        is_home: boolean;
        kickoff_at: string;
      }>;
      avg_opponent_rank: number | null;
    };
  };
  bonuses?: BonusAward[];
  scoring_events?: ScoringEventMatch[];
  recent_matches: TeamFixture[];
  upcoming_matches: TeamFixture[];
}

export interface ManagerClub {
  team_id: UUID;
  team_name: string;
  crest_url: string | null;
  pool_id: UUID | null;
  pool_name: string | null;
  pool_sort_order?: number;
  acquired_via: string | null;
  draft_pick_number?: number | null;
  points: number;
  games_played: number;
  points_per_game: number;
}

/** @deprecated Use ManagerClub */
export type MemberClub = ManagerClub;

export interface ManagerDetail {
  id: UUID;
  team_name: string | null;
  display_name: string | null;
  draft_slot: number | null;
  rank: number | null;
  stats: {
    total_points: number;
    games_played: number;
    wins: number;
    draws: number;
    losses: number;
    upset_points: number;
    bonus_points: number;
    points_per_game: number;
    event_points_by_type?: Record<string, number>;
    event_counts_by_type?: Record<string, number>;
    bonus_points_by_type?: Record<string, number>;
  };
  clubs: ManagerClub[];
  bonuses?: BonusAward[];
}

/** @deprecated Use ManagerDetail */
export type MemberDetail = ManagerDetail;

export interface ManagerHighlights {
  member_id: UUID;
  display_name: string;
  best_matchweek: { scheduled_matchweek: number; points: number } | null;
  worst_matchweek: { scheduled_matchweek: number; points: number } | null;
  biggest_upset: {
    event_type: string;
    points: number;
    gap: number | null;
    match_id: UUID | null;
    team_id: UUID | null;
    team_name: string | null;
    opponent_name?: string | null;
    underdog_rank?: number | null;
    opponent_rank?: number | null;
  } | null;
  top_club: { team_id: UUID; team_name: string; points: number } | null;
}

/** @deprecated Use ManagerHighlights */
export type MemberHighlights = ManagerHighlights;

export interface VenueSplitRow {
  member_id: UUID;
  display_name: string;
  team_id: UUID | null;
  team_name: string | null;
  home: VenueSplit;
  away: VenueSplit;
}

export interface Snapshot {
  id: UUID;
  pool_id: UUID;
  kickoff_at: string;
  stale?: boolean;
  computed_at: string;
  rows: Array<{
    team_id: UUID | null;
    team_name: string | null;
    position: number;
    played: number;
    points: number;
    goals_for?: number;
    goals_against?: number;
    goal_difference?: number;
  }>;
}

export interface PpgRow {
  team_id: UUID | null;
  team_name: string | null;
  member_id: UUID | null;
  display_name: string | null;
  points: number;
  games_played: number;
  points_per_game: number;
}

export interface MatchweekRow {
  member_id: UUID;
  display_name: string;
  scheduled_matchweek: number;
  points: number;
}

export interface UpsetRow {
  member_id: UUID;
  display_name: string;
  count: number;
  points: number;
  upset_count?: number;
  upset_points?: number;
  by_type?: Record<string, number>;
}

/** @deprecated Prefer typed analytics row interfaces. */
export type AnalyticsRow = Record<string, string | number | null | Record<string, Json>>;

export interface Message {
  detail: string;
}

/** Normalize API league detail into the shape components expect. */
export function normalizeLeague(raw: League): League {
  const pools = (raw.pools || []).map((p) => ({
    ...p,
    // Prefer backend `label`/`key`/`slot_count`; keep thin aliases for older UI.
    name: p.label || p.name || p.key,
    definition_key: p.key || p.definition_key,
    roster_size: p.slot_count ?? p.roster_size ?? 0,
    scoring_enabled: p.scores_match_results ?? p.scoring_enabled ?? true,
  }));
  const max =
    raw.max_members ??
    (typeof raw.settings?.max_members === "number" ? raw.settings.max_members : null);
  const rosterOrder =
    raw.roster_club_order === "competition" || raw.settings?.roster_club_order === "competition"
      ? "competition"
      : "draft";
  return {
    ...raw,
    season_label: raw.season_label || raw.season || "",
    season: raw.season_label || raw.season || "",
    max_members: max,
    roster_club_order: rosterOrder,
    visibility: raw.visibility || "private",
    role: raw.role || (raw.members?.find((m) => m.id === raw.current_member_id)?.role) || "member",
    pools,
    members: (raw.members || []).map((m) => ({
      ...m,
      display_name: m.display_name || m.email || "Manager",
      team_name: m.team_name?.trim() || null,
      role: m.role || (m.is_commissioner ? "commissioner" : "member"),
    })),
  };
}
