import { humanizeKey } from "@/components/settings/types";

/** Built-in labels for match-result scoring events. */
export const SCORING_EVENT_LABELS: Record<string, string> = {
  win: "Win",
  win_et: "Win (extra time)",
  win_pk: "Win (penalties)",
  draw: "Draw",
  loss: "Loss",
  loss_et: "Loss (extra time)",
  loss_pk: "Loss (penalties)",
  minor_upset: "Minor upset",
  major_upset: "Major upset",
  major_upset_draw: "Major upset draw",
  bonus: "Bonus awards",
};

/**
 * Customer-facing label for a scoring event type.
 * Prefer league upset threshold names (`customLabels`), then built-ins — never raw keys.
 */
export function scoringEventLabel(
  key: string,
  customLabels?: Record<string, string>,
): string {
  const custom = customLabels?.[key]?.trim();
  if (custom) return custom;
  return SCORING_EVENT_LABELS[key] || humanizeKey(key);
}
