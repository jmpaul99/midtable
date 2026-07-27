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

/** H2H scoreline, e.g. `2–1` or `—–—`. */
export function formatScoreline(
  homeGoals: number | null | undefined,
  awayGoals: number | null | undefined,
): string {
  return `${homeGoals ?? "—"}–${awayGoals ?? "—"}`;
}

/** Team-oriented scoreline (own goals first when away). */
export function formatTeamOrientedScoreline(m: {
  is_home: boolean;
  home_goals: number | null | undefined;
  away_goals: number | null | undefined;
}): string {
  return m.is_home
    ? formatScoreline(m.home_goals, m.away_goals)
    : formatScoreline(m.away_goals, m.home_goals);
}

/** Autocomplete / select label for a match log row. */
export function formatMatchOptionLabel(m: {
  home_team_name: string;
  away_team_name: string;
  home_goals?: number | null;
  away_goals?: number | null;
  scheduled_matchweek?: number | null;
}): string {
  const score =
    m.home_goals != null && m.away_goals != null
      ? ` ${m.home_goals}-${m.away_goals}`
      : "";
  const mw = m.scheduled_matchweek != null ? ` · MW${m.scheduled_matchweek}` : "";
  return `${m.home_team_name} vs ${m.away_team_name}${score}${mw}`;
}
