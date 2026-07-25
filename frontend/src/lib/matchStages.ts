export type MatchStage = {
  code: string;
  label: string;
};

/** Football-data.org / API stage codes with display labels. */
export const MATCH_STAGES: MatchStage[] = [
  { code: "FINAL", label: "Final" },
  { code: "THIRD_PLACE", label: "Third place" },
  { code: "SEMI_FINALS", label: "Semi-finals" },
  { code: "QUARTER_FINALS", label: "Quarter-finals" },
  { code: "LAST_16", label: "Round of 16" },
  { code: "LAST_32", label: "Round of 32" },
  { code: "LAST_64", label: "Round of 64" },
  { code: "ROUND_4", label: "Round 4" },
  { code: "ROUND_3", label: "Round 3" },
  { code: "ROUND_2", label: "Round 2" },
  { code: "ROUND_1", label: "Round 1" },
  { code: "GROUP_STAGE", label: "Group stage" },
  { code: "PRELIMINARY_ROUND", label: "Preliminary round" },
  { code: "QUALIFICATION", label: "Qualification" },
  { code: "QUALIFICATION_ROUND_1", label: "Qualification round 1" },
  { code: "QUALIFICATION_ROUND_2", label: "Qualification round 2" },
  { code: "QUALIFICATION_ROUND_3", label: "Qualification round 3" },
  { code: "PLAYOFF_ROUND_1", label: "Playoff round 1" },
  { code: "PLAYOFF_ROUND_2", label: "Playoff round 2" },
  { code: "PLAYOFFS", label: "Playoffs" },
  { code: "REGULAR_SEASON", label: "Regular season" },
  { code: "CHAMPIONSHIP_ROUND", label: "Championship round" },
  { code: "RELEGATION_ROUND", label: "Relegation round" },
];

const byCode = new Map(MATCH_STAGES.map((s) => [s.code, s.label]));

export function matchStageLabel(code: string): string {
  const known = byCode.get(code);
  if (known) return known;
  return code
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

export function filterMatchStages(query: string, exclude: Set<string> = new Set()): MatchStage[] {
  const q = query.trim().toLowerCase();
  return MATCH_STAGES.filter((s) => {
    if (exclude.has(s.code)) return false;
    if (!q) return true;
    return s.label.toLowerCase().includes(q) || s.code.toLowerCase().includes(q);
  });
}

const stageOrder = new Map(MATCH_STAGES.map((s, i) => [s.code, i]));

/** Ordered entries for UI; empty if ≤1 stage (hide single-stage competitions). */
export function multiStagePointsEntries(
  pointsByStage: Record<string, number> | null | undefined,
): Array<{ code: string; label: string; points: number }> {
  const entries = Object.entries(pointsByStage || {}).filter(([code]) => Boolean(code));
  if (entries.length <= 1) return [];
  return entries
    .map(([code, points]) => ({
      code,
      label: matchStageLabel(code),
      points: Number(points) || 0,
    }))
    .sort((a, b) => {
      const ai = stageOrder.get(a.code) ?? 999;
      const bi = stageOrder.get(b.code) ?? 999;
      if (ai !== bi) return ai - bi;
      return a.label.localeCompare(b.label);
    });
}
