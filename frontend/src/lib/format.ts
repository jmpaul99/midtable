export function formatNumber(value: string | number) {
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function formatDate(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "—";
}

/** Local date/time with short timezone name (e.g. PDT) — use for scheduled draft starts. */
export function formatDateTimeWithZone(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, { timeZoneName: "short" });
}

/** Live countdown label: `M:SS`, `H:MM:SS`, or `Nd H:MM:SS`. */
export function formatCountdownDuration(ms: number): string {
  if (ms <= 0) return "0:00";
  const totalSec = Math.ceil(ms / 1000);
  const days = Math.floor(totalSec / 86_400);
  const hours = Math.floor((totalSec % 86_400) / 3_600);
  const mins = Math.floor((totalSec % 3_600) / 60);
  const secs = totalSec % 60;
  const mm = String(mins).padStart(2, "0");
  const ss = String(secs).padStart(2, "0");
  if (days > 0) return `${days}d ${hours}:${mm}:${ss}`;
  if (hours > 0) return `${hours}:${mm}:${ss}`;
  return `${mins}:${ss}`;
}

/** True when both sides have a recorded goal count. */
export function hasScoreline(
  homeGoals: number | null | undefined,
  awayGoals: number | null | undefined,
): boolean {
  return homeGoals != null && awayGoals != null;
}

/** H2H scoreline, e.g. `2–1`. Null when either side is unplayed / missing. */
export function formatScoreline(
  homeGoals: number | null | undefined,
  awayGoals: number | null | undefined,
): string | null {
  if (!hasScoreline(homeGoals, awayGoals)) return null;
  return `${homeGoals}–${awayGoals}`;
}

/** Team-oriented scoreline (own goals first when away). Null when unplayed. */
export function formatTeamOrientedScoreline(m: {
  is_home: boolean;
  home_goals: number | null | undefined;
  away_goals: number | null | undefined;
}): string | null {
  return m.is_home
    ? formatScoreline(m.home_goals, m.away_goals)
    : formatScoreline(m.away_goals, m.home_goals);
}

export type PeriodKind = "matchweek" | "round";

export function periodKind(competitionType: string | null | undefined): PeriodKind {
  return competitionType === "LEAGUE" ? "matchweek" : "round";
}

/** Short ordinal label: MW3 or R3. */
export function formatPeriodShort(
  n: number,
  competitionType: string | null | undefined,
): string {
  return periodKind(competitionType) === "matchweek" ? `MW${n}` : `R${n}`;
}

export function formatPeriodLong(
  n: number,
  competitionType: string | null | undefined,
): string {
  const word = periodKind(competitionType) === "matchweek" ? "Matchweek" : "Round";
  return `${word} ${n}`;
}

export function formatPeriodRange(
  from: number,
  to: number,
  competitionType: string | null | undefined,
): string {
  const word = periodKind(competitionType) === "matchweek" ? "Matchweeks" : "Rounds";
  return `${word} ${from}–${to}`;
}

export function formatPeriodNoun(
  competitionType: string | null | undefined,
  opts?: { plural?: boolean; capitalize?: boolean },
): string {
  const plural = opts?.plural ?? false;
  const capitalize = opts?.capitalize ?? true;
  let word =
    periodKind(competitionType) === "matchweek"
      ? plural
        ? "Matchweeks"
        : "Matchweek"
      : plural
        ? "Rounds"
        : "Round";
  if (!capitalize) word = word.toLowerCase();
  return word;
}

/** Scoring pool competition.type for league-level copy. */
export function scoringCompetitionType(
  pools:
    | Array<{
        scores_match_results?: boolean;
        competition_type?: string | null;
        sort_order?: number;
      }>
    | null
    | undefined,
): string | null {
  if (!pools?.length) return null;
  const scoring = pools.filter((p) => p.scores_match_results !== false);
  const list = (scoring.length ? scoring : pools).slice().sort((a, b) => {
    const ao = a.sort_order ?? 0;
    const bo = b.sort_order ?? 0;
    return ao - bo;
  });
  for (const p of list) {
    if (p.competition_type) return p.competition_type;
  }
  return null;
}

/** Autocomplete / select label for a match log row. */
export function formatMatchOptionLabel(
  m: {
    home_team_name: string;
    away_team_name: string;
    home_goals?: number | null;
    away_goals?: number | null;
    scheduled_matchweek?: number | null;
  },
  competitionType?: string | null,
): string {
  const score =
    m.home_goals != null && m.away_goals != null
      ? ` ${m.home_goals}-${m.away_goals}`
      : "";
  const mw =
    m.scheduled_matchweek != null
      ? ` · ${formatPeriodShort(m.scheduled_matchweek, competitionType)}`
      : "";
  return `${m.home_team_name} vs ${m.away_team_name}${score}${mw}`;
}
