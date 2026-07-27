"use client";

import type { ReactNode } from "react";
import type { League } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { Card, Muted, RankBadge, Stack } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { ManagerLink } from "./ManagerLink";

function ReviewBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-surface-2/40 px-3 py-2.5">
      <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-muted">{title}</h4>
      <div className="space-y-0.5 font-semibold text-ink">{children}</div>
    </div>
  );
}

function humanizeKey(key: string): string {
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function preassignLabel(mode: string): string {
  if (mode === "none") return "None";
  if (mode === "supported") return "Supported";
  if (mode === "optional") return "Optional";
  return humanizeKey(mode);
}

function draftOrderMembers(league: League) {
  return [...(league.members || [])].sort((a, b) => {
    const as = a.draft_slot ?? 10_000;
    const bs = b.draft_slot ?? 10_000;
    if (as !== bs) return as - bs;
    return managerLabel(a).localeCompare(managerLabel(b));
  });
}

function DraftOrderList({
  league,
  onClockMemberId,
}: {
  league: League;
  onClockMemberId?: string | null;
}) {
  const ordered = draftOrderMembers(league);
  if (!ordered.length) {
    return <div className="text-muted">No managers yet</div>;
  }
  return (
    <ul className="flex flex-col gap-1.5">
      {ordered.map((m, index) => {
        const onClock = Boolean(onClockMemberId && m.id === onClockMemberId);
        return (
          <li
            key={m.id}
            className={cn(
              "flex items-center gap-2 rounded-lg border px-2.5 py-2",
              onClock
                ? "border-brand/40 bg-brand/10"
                : "border-line/60 bg-surface/60",
            )}
          >
            <RankBadge value={m.draft_slot ?? index + 1} />
            <div className="min-w-0 flex-1">
              <ManagerLink leagueId={league.id} managerId={m.id}>
                <span className="truncate font-bold">{managerLabel(m)}</span>
              </ManagerLink>
              {onClock && <Muted className="text-xs">On the clock</Muted>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function DraftSettingsSummary({
  league,
  scheduledAt,
  pickTimerSeconds,
  onClockMemberId = null,
  compact = false,
}: {
  league: League;
  scheduledAt?: string | null;
  pickTimerSeconds?: number | null;
  onClockMemberId?: string | null;
  /** Live draft: style + timer line and order with on-clock highlight. */
  compact?: boolean;
}) {
  const style = league.draft_style === "snake" ? "Snake" : "Linear";
  const preassign = preassignLabel(league.preassign_mode || "none");
  const timer =
    pickTimerSeconds != null && pickTimerSeconds > 0
      ? `${pickTimerSeconds}s per pick`
      : "Off";
  const schedule = scheduledAt ? formatDate(scheduledAt) : "Not scheduled";

  if (compact) {
    return (
      <Card>
        <Stack gap="sm">
          <h2>Draft order</h2>
          <Muted className="text-xs">
            {style} · Pick timer: {timer}
          </Muted>
          <DraftOrderList league={league} onClockMemberId={onClockMemberId} />
        </Stack>
      </Card>
    );
  }

  return (
    <Card>
      <Stack>
        <h2>Draft settings</h2>
        <div className="flex flex-col gap-3 text-sm">
          <ReviewBlock title="Basics">
            <div>
              Style: {style}
              {" · "}
              Preassign: {preassign}
            </div>
            <div>Scheduled start: {schedule}</div>
            <div>Pick timer: {timer}</div>
          </ReviewBlock>
          <ReviewBlock title="Draft order">
            <DraftOrderList league={league} onClockMemberId={onClockMemberId} />
          </ReviewBlock>
        </div>
      </Stack>
    </Card>
  );
}
