/** Curated football-data.org free-plan competitions. */

export type AvailableCompetition = {
  code: string;
  label: string;
  key: string;
};

export const AVAILABLE_COMPETITIONS: AvailableCompetition[] = [
  { code: "WC", label: "FIFA World Cup", key: "fifa_world_cup" },
  { code: "CL", label: "UEFA Champions League", key: "uefa_champions_league" },
  { code: "BL1", label: "Bundesliga", key: "bundesliga" },
  { code: "DED", label: "Eredivisie", key: "eredivisie" },
  {
    code: "BSA",
    label: "Campeonato Brasileiro Série A",
    key: "campeonato_brasileiro_serie_a",
  },
  { code: "PD", label: "Primera Division", key: "primera_division" },
  { code: "FL1", label: "Ligue 1", key: "ligue_1" },
  { code: "ELC", label: "Championship", key: "championship" },
  { code: "PPL", label: "Primeira Liga", key: "primeira_liga" },
  { code: "EC", label: "European Championship", key: "european_championship" },
  { code: "SA", label: "Serie A", key: "serie_a" },
  { code: "PL", label: "Premier League", key: "premier_league" },
];

export function findAvailableCompetition(
  code: string | null | undefined,
): AvailableCompetition | undefined {
  if (!code) return undefined;
  const normalized = code.trim().toUpperCase();
  return AVAILABLE_COMPETITIONS.find((c) => c.code === normalized);
}

export function competitionDisplayLabel(
  code: string | null | undefined,
  fallbackLabel?: string | null,
): string {
  const entry = findAvailableCompetition(code);
  if (entry) return entry.label;
  return (fallbackLabel || code || "").trim();
}

/**
 * football-data.org season filter uses the season start year
 * (e.g. 2026 for 2026/27). European seasons typically turn over in July/August.
 */
export function defaultFootballSeasonYear(now: Date = new Date()): number {
  const year = now.getFullYear();
  const month = now.getMonth() + 1; // 1–12
  return month >= 7 ? year : year - 1;
}

export function filterAvailableCompetitions(
  query: string,
  options: AvailableCompetition[] = AVAILABLE_COMPETITIONS,
): AvailableCompetition[] {
  const q = query.trim().toLowerCase();
  if (!q) return options;
  return options.filter(
    (c) =>
      c.label.toLowerCase().includes(q) ||
      c.code.toLowerCase().includes(q) ||
      c.key.toLowerCase().includes(q),
  );
}
