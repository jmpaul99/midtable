import type { ReactNode } from "react";
import type { LeaderboardPhase } from "@/components/settings";

export function ReviewBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-0 max-w-full overflow-hidden rounded-xl border border-line bg-surface-2/40 px-3 py-2.5">
      <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-muted">{title}</h4>
      <div className="min-w-0 space-y-0.5 font-semibold text-ink">{children}</div>
    </div>
  );
}

function humanizeKey(key: string): string {
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function formatPhaseFilter(filter: LeaderboardPhase["match_filter"]): string {
  if (filter.type === "matchweek_range") {
    return `Matchweeks ${filter.from}–${filter.to}`;
  }
  if (filter.type === "stage_in") {
    return filter.stages.length
      ? `Stages: ${filter.stages.map(humanizeKey).join(", ")}`
      : "Stages: none";
  }
  return "—";
}
