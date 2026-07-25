"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { formatDate, formatNumber } from "@/lib/format";
import type { BonusAward, ScoringEventMatch, UUID } from "@/lib/types";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { TeamLink } from "./TeamLink";
import { cn } from "@/lib/cn";

const CATEGORY_ORDER = [
  "win",
  "draw",
  "minor_upset",
  "major_upset",
  "major_upset_draw",
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  win: "Wins",
  draw: "Draws",
  minor_upset: "Minor upsets",
  major_upset: "Major upsets",
  major_upset_draw: "Major upset draws",
  bonus: "Bonus awards",
};

function categoryLabel(key: string, labels?: Record<string, string>) {
  return labels?.[key] || CATEGORY_LABELS[key] || key.replaceAll("_", " ");
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className={cn(
        "size-5 shrink-0 text-muted transition-transform duration-200",
        open && "rotate-180",
      )}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function CategoryRow({
  label,
  count,
  points,
  open,
  expandable,
  onToggle,
  children,
}: {
  label: string;
  count: number;
  points: number;
  open: boolean;
  expandable: boolean;
  onToggle: () => void;
  children?: React.ReactNode;
}) {
  const summary = (
    <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
      <div className="min-w-0">
        <strong className="block truncate capitalize">{label}</strong>
        <Muted className="text-xs tabular-nums">
          {count === 0 ? "None yet" : `${count}×`}
          {expandable ? (open ? " · hide" : " · expand") : ""}
        </Muted>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className="font-display text-lg font-extrabold tabular-nums">
          {formatNumber(points)}
        </span>
        {expandable && <Chevron open={open} />}
      </div>
    </div>
  );

  if (!expandable) {
    return (
      <li className="rounded-xl border border-line bg-surface-2/40 px-3 py-2.5">{summary}</li>
    );
  }

  return (
    <li className="overflow-hidden rounded-xl border border-line bg-surface-2/40">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="flex min-h-12 w-full items-center gap-2 px-3 py-2.5 text-left transition hover:bg-surface-2"
      >
        {summary}
      </button>
      {open && <div className="border-t border-line px-3 py-2.5">{children}</div>}
    </li>
  );
}

export function TeamScoringBreakdown({
  leagueId,
  events,
  bonuses,
  bonusPoints,
  eventPointsByType,
  eventCountsByType,
  eventTypeLabels,
}: {
  leagueId: UUID;
  events: ScoringEventMatch[];
  bonuses: BonusAward[];
  bonusPoints: number;
  eventPointsByType?: Record<string, number>;
  eventCountsByType?: Record<string, number>;
  /** Upset threshold key → display name from league settings. */
  eventTypeLabels?: Record<string, string>;
}) {
  const [openKey, setOpenKey] = useState<string | null>(null);

  const eventsByType = useMemo(() => {
    const map = new Map<string, ScoringEventMatch[]>();
    for (const event of events) {
      const list = map.get(event.event_type) || [];
      list.push(event);
      map.set(event.event_type, list);
    }
    return map;
  }, [events]);

  const categories = useMemo(() => {
    const keys = new Set<string>([
      ...CATEGORY_ORDER,
      ...Object.keys(eventPointsByType || {}),
      ...eventsByType.keys(),
    ]);
    keys.delete("bonus");

    const ordered = [
      ...CATEGORY_ORDER.filter((k) => keys.has(k)),
      ...[...keys].filter((k) => !(CATEGORY_ORDER as readonly string[]).includes(k)).sort(),
    ];

    return ordered
      .map((key) => {
        const matchEvents = eventsByType.get(key) || [];
        const points =
          eventPointsByType?.[key] ??
          matchEvents.reduce((n, e) => n + e.points, 0);
        const count = eventCountsByType?.[key] ?? matchEvents.length;
        return { key, points, count, matchEvents };
      })
      .filter((c) => c.points > 0 || c.count > 0);
  }, [eventPointsByType, eventCountsByType, eventsByType]);

  // Always show at least the known scoring + bonus rows when anything exists,
  // and always show bonus so the category is discoverable.
  const hasAnyPoints =
    categories.some((c) => c.points > 0) || bonusPoints > 0 || bonuses.length > 0;

  if (!hasAnyPoints && categories.length === 0) {
    return (
      <Card className="min-w-0 overflow-hidden">
        <Stack>
          <h2>Points breakdown</h2>
          <Muted className="text-sm">No scoring events or bonus awards yet.</Muted>
        </Stack>
      </Card>
    );
  }

  const toggle = (key: string) => setOpenKey((cur) => (cur === key ? null : key));

  return (
    <Card className="min-w-0 overflow-hidden">
      <Stack>
        <div>
          <Eyebrow>Fantasy points</Eyebrow>
          <h2>Points breakdown</h2>
          <Muted className="mt-1 text-sm">
            Expand upset categories to see the matches that earned them.
          </Muted>
        </div>
        <ul className="flex flex-col gap-2">
          {categories.map((cat) => {
            const expandable = cat.matchEvents.length > 0;
            const open = openKey === cat.key;
            return (
              <CategoryRow
                key={cat.key}
                label={categoryLabel(cat.key, eventTypeLabels)}
                count={cat.count}
                points={cat.points}
                open={open}
                expandable={expandable}
                onToggle={() => toggle(cat.key)}
              >
                <ul className="flex flex-col gap-2">
                  {cat.matchEvents.map((e) => {
                    const gap =
                      typeof e.metadata?.gap === "number" ? e.metadata.gap : null;
                    const score = e.is_home
                      ? `${e.home_goals ?? "—"}–${e.away_goals ?? "—"}`
                      : `${e.away_goals ?? "—"}–${e.home_goals ?? "—"}`;
                    return (
                      <li key={e.id}>
                        <Link
                          href={`/leagues/${leagueId}/matches/${e.match_id}`}
                          className="block rounded-lg border border-line bg-surface px-3 py-2.5 transition hover:border-brand/40"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <Muted className="text-[11px] sm:text-xs">
                                {formatDate(e.kickoff_at)}
                                {e.scheduled_matchweek != null
                                  ? ` · MW${e.scheduled_matchweek}`
                                  : ""}
                                {e.is_home ? " · Home" : " · Away"}
                                {gap != null ? ` · Gap ${gap}` : ""}
                              </Muted>
                              <strong className="mt-0.5 block truncate text-sm">
                                vs{" "}
                                <TeamLink leagueId={leagueId} teamId={e.opponent_id}>
                                  {e.opponent_name}
                                </TeamLink>
                              </strong>
                            </div>
                            <div className="shrink-0 text-right">
                              <div className="font-display text-sm font-extrabold tabular-nums">
                                {score}
                              </div>
                              <Muted className="text-[11px] tabular-nums">
                                +{formatNumber(e.points)} pts
                              </Muted>
                            </div>
                          </div>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </CategoryRow>
            );
          })}

          <CategoryRow
            label={categoryLabel("bonus")}
            count={bonuses.length}
            points={bonusPoints}
            open={openKey === "bonus"}
            expandable
            onToggle={() => toggle("bonus")}
          >
            {!bonuses.length ? (
              <Muted className="text-sm">No bonus awards for this club yet.</Muted>
            ) : (
              <ul className="flex flex-col gap-2">
                {bonuses.map((b) => (
                  <li
                    key={b.id}
                    className="rounded-lg border border-line bg-surface px-3 py-2.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <strong className="block truncate text-sm">
                          {b.bonus_type_label || b.bonus_type}
                        </strong>
                        {b.reason && (
                          <p className="mt-1 break-words text-xs text-muted">{b.reason}</p>
                        )}
                        {b.awarded_at && (
                          <Muted className="mt-1 text-[11px]">
                            Awarded {formatDate(b.awarded_at)}
                          </Muted>
                        )}
                      </div>
                      <div className="shrink-0 font-display text-sm font-extrabold tabular-nums">
                        +{formatNumber(b.points)}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CategoryRow>
        </ul>
      </Stack>
    </Card>
  );
}
