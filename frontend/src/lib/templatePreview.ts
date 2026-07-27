import { competitionDisplayLabel } from "@/lib/availableCompetitions";
import type { CompetitionTemplate, Json } from "@/lib/types";

type PoolDef = {
  label?: string;
  competition_code?: string;
  scores_match_results?: boolean;
  key?: string;
};

type RosterSlot = {
  count?: number;
  label?: string;
  pool_key?: string;
};

type PhaseDef = {
  label?: string;
};

function asRecord(value: Json | undefined): Record<string, Json> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, Json>;
}

function parsePools(template: CompetitionTemplate): PoolDef[] {
  return (template.pool_definitions || [])
    .map((raw) => asRecord(raw))
    .filter((row): row is Record<string, Json> => row != null)
    .map((row) => ({
      label: typeof row.label === "string" ? row.label : undefined,
      competition_code:
        typeof row.competition_code === "string" ? row.competition_code : undefined,
      scores_match_results: row.scores_match_results === true,
      key: typeof row.key === "string" ? row.key : undefined,
    }));
}

function parseRosterSlots(template: CompetitionTemplate): RosterSlot[] {
  return (template.roster_slots || [])
    .map((raw) => asRecord(raw))
    .filter((row): row is Record<string, Json> => row != null)
    .map((row) => ({
      count: typeof row.count === "number" ? row.count : Number(row.count) || 0,
      label: typeof row.label === "string" ? row.label : undefined,
      pool_key: typeof row.pool_key === "string" ? row.pool_key : undefined,
    }));
}

function parsePhases(template: CompetitionTemplate): PhaseDef[] {
  return (template.leaderboard_phases || [])
    .map((raw) => asRecord(raw as Json))
    .filter((row): row is Record<string, Json> => row != null)
    .map((row) => ({
      label: typeof row.label === "string" ? row.label : undefined,
    }));
}

function shortRosterLabel(slot: RosterSlot, pools: PoolDef[]): string {
  const raw = (slot.label || "").trim().replace(/\s+team$/i, "").trim();
  if (raw) return raw;
  const pool = pools.find((p) => p.key && p.key === slot.pool_key);
  if (pool) {
    return competitionDisplayLabel(pool.competition_code, pool.label) || pool.key || "clubs";
  }
  return "clubs";
}

function capList(items: string[], limit = 2): string {
  if (items.length <= limit) return items.join(", ");
  const shown = items.slice(0, limit);
  return `${shown.join(", ")} +${items.length - limit}`;
}

export type TemplatePreviewMeta = {
  competitions: string;
  competitionLines: string[];
  roster: string;
  rosterLines: string[];
  members: string;
  phases: string;
  scoring: string;
};

export function formatTemplatePreviewMeta(
  template: CompetitionTemplate,
): TemplatePreviewMeta {
  const pools = parsePools(template);
  const slots = parseRosterSlots(template);
  const phases = parsePhases(template);

  const competitionLines = pools.map((pool) => {
    const name =
      competitionDisplayLabel(pool.competition_code, pool.label) ||
      pool.label ||
      pool.competition_code ||
      "Competition";
    return pool.scores_match_results === false ? `${name} (not scored)` : name;
  });
  const competitions = competitionLines.length
    ? capList(competitionLines)
    : "—";

  const rosterLines = slots
    .filter((s) => (s.count || 0) > 0)
    .map((s) => {
      const count = s.count || 0;
      if (pools.length <= 1) return String(count);
      return `${count} ${shortRosterLabel(s, pools)}`;
    });
  const roster = rosterLines.length ? rosterLines.join(" + ") : "—";

  const members =
    template.max_members != null && template.max_members > 0
      ? String(template.max_members)
      : "—";

  const phaseLabels = phases
    .map((p) => (p.label || "").trim())
    .filter(Boolean);
  const phasesText = phaseLabels.length ? capList(phaseLabels) : "—";

  const scoringParts: string[] = [];
  const points = asRecord(template.result_points as Json);
  const win =
    points && (typeof points.win === "number" || typeof points.win === "string")
      ? Number(points.win)
      : null;
  const draw =
    points && (typeof points.draw === "number" || typeof points.draw === "string")
      ? Number(points.draw)
      : null;
  if (win != null && !Number.isNaN(win) && draw != null && !Number.isNaN(draw)) {
    scoringParts.push(`${win}/${draw}`);
  }
  const upsetEnabled = asRecord(template.upset_rules as Json)?.enabled === true;
  if (upsetEnabled) scoringParts.push("Upsets");
  if ((template.bonus_types || []).length > 0) scoringParts.push("Bonuses");
  const scoring = scoringParts.length ? scoringParts.join(" · ") : "—";

  return {
    competitions,
    competitionLines,
    roster,
    rosterLines,
    members,
    phases: phasesText,
    scoring,
  };
}
