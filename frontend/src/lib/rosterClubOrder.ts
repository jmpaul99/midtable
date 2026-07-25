/** How clubs are ordered within a manager’s roster. */

export type RosterClubOrder = "draft" | "competition";

export type RosterClubSortable = {
  acquired_via?: string | null;
  draft_pick_number?: number | null;
  pool_sort_order?: number | null;
  slot_number?: number | null;
  pool_name?: string | null;
  team_name?: string | null;
  team_id?: string | null;
};

export function normalizeRosterClubOrder(value: unknown): RosterClubOrder {
  return value === "competition" ? "competition" : "draft";
}

/** Pre-draft always uses competition order; after draft opens, use the league setting. */
export function effectiveRosterClubOrder(
  leagueStatus: string | null | undefined,
  configured: RosterClubOrder | null | undefined,
): RosterClubOrder {
  if (leagueStatus === "pre_draft") return "competition";
  return configured === "competition" ? "competition" : "draft";
}

function draftRank(row: RosterClubSortable, emptyRank = 10_000): number {
  if ((row.acquired_via || "").toLowerCase() === "preassigned") return 0;
  if (row.draft_pick_number != null) return row.draft_pick_number;
  if (row.team_id) return emptyRank;
  return emptyRank + 10_000;
}

export function compareRosterClubs(
  a: RosterClubSortable,
  b: RosterClubSortable,
  mode: RosterClubOrder,
): number {
  const byDraft = draftRank(a) - draftRank(b);
  const byPool = (a.pool_sort_order ?? 999) - (b.pool_sort_order ?? 999);
  const bySlot =
    (a.slot_number ?? 0) - (b.slot_number ?? 0) ||
    (a.pool_name || "").localeCompare(b.pool_name || "") ||
    (a.team_name || "").localeCompare(b.team_name || "");

  if (mode === "competition") {
    if (byPool !== 0) return byPool;
    if (byDraft !== 0) return byDraft;
    return bySlot;
  }
  if (byDraft !== 0) return byDraft;
  if (byPool !== 0) return byPool;
  return bySlot;
}
