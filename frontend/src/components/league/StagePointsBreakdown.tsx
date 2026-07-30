"use client";

import { formatNumber } from "@/lib/format";
import { multiStagePointsEntries } from "@/lib/matchStages";
import { cn } from "@/lib/cn";
import { Muted } from "@/components/ui/Card";

export type PeriodPointsRow = {
  period_key: string;
  label: string;
  points: number;
};

export function PeriodPointsBreakdown({
  periods,
  compact = false,
  className,
}: {
  periods?: PeriodPointsRow[] | null;
  compact?: boolean;
  className?: string;
}) {
  const rows = (periods || []).filter((r) => r.period_key);
  if (rows.length <= 1) return null;

  if (compact) {
    return (
      <ul className={cn("mt-1.5 flex flex-col gap-0.5 text-xs tabular-nums text-muted", className)}>
        {rows.map((r) => (
          <li key={r.period_key} className="flex items-center justify-between gap-2">
            <span className="min-w-0 truncate">{r.label}</span>
            <span className="shrink-0 font-semibold text-ink">{formatNumber(r.points)}</span>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <h2>By period</h2>
      <Muted className="text-xs">
        Fantasy points from finished matches in each competition period.
      </Muted>
      <ul className="flex flex-col gap-2">
        {rows.map((r) => (
          <li
            key={r.period_key}
            className="flex items-center justify-between gap-2 rounded-xl border border-line bg-surface-2/40 px-3 py-2.5 text-sm"
          >
            <span className="min-w-0 truncate font-semibold">{r.label}</span>
            <span className="shrink-0 tabular-nums text-muted">{formatNumber(r.points)} pts</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Fallback when only flat stage totals are available. */
export function StagePointsBreakdown({
  pointsByStage,
  compact = false,
  className,
}: {
  pointsByStage?: Record<string, number> | null;
  compact?: boolean;
  className?: string;
}) {
  const rows = multiStagePointsEntries(pointsByStage).map((r) => ({
    period_key: r.code,
    label: r.label,
    points: r.points,
  }));
  return <PeriodPointsBreakdown periods={rows} compact={compact} className={className} />;
}
