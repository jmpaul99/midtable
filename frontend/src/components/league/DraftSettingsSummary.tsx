"use client";

import type { ReactNode } from "react";
import type { League } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { formatDateTimeWithZone } from "@/lib/format";
import { Card, RankBadge, Stack } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { ManagerLink } from "./ManagerLink";

function ReviewBlock({ title, children }: { title: string; children: ReactNode }) {
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

function preassignLabel(mode: string, count?: number): string {
  const n = count != null && Number.isFinite(count) ? Math.floor(count) : null;
  if (mode === "off" || mode === "none") return "Off";
  if (mode === "required" || mode === "supported") {
    return n != null ? `Required (${n})` : "Required";
  }
  if (mode === "optional") {
    return n != null ? `Optional (max ${n})` : "Optional";
  }
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
}: {
  league: League;
  scheduledAt?: string | null;
  pickTimerSeconds?: number | null;
  onClockMemberId?: string | null;
}) {
  const preassign = league.preassign_mode || "off";
  const preassignCount =
    league.preassign_count ??
    (typeof league.settings?.preassign_count === "number"
      ? league.settings.preassign_count
      : undefined);
  const schedule =
    scheduledAt ??
    league.draft_scheduled_at ??
    (typeof league.settings?.draft_scheduled_at === "string"
      ? league.settings.draft_scheduled_at
      : null);
  const timerSeconds =
    pickTimerSeconds ??
    league.pick_timer_seconds ??
    (typeof league.settings?.pick_timer_seconds === "number"
      ? league.settings.pick_timer_seconds
      : null);

  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <Stack className="min-w-0">
        <h2>Draft settings</h2>
        <div className="flex min-w-0 flex-col gap-3 text-sm">
          <div className="min-w-0 max-w-full space-y-0.5 overflow-hidden rounded-xl border border-line bg-surface-2/40 px-3 py-2.5 font-semibold text-ink">
            <div>Status: {humanizeKey(league.status || "unknown")}</div>
            <div>
              Style: {league.draft_style === "snake" ? "Snake" : "Linear"}
            </div>
            <div>
              Preassign clubs before draft: {preassignLabel(preassign, preassignCount)}
            </div>
            <div>
              Scheduled start:{" "}
              {schedule
                ? formatDateTimeWithZone(schedule)
                : "Not set (open manually)"}
            </div>
            <div>
              Pick timer:{" "}
              {timerSeconds != null && timerSeconds > 0
                ? `${timerSeconds}s`
                : "Off"}
            </div>
          </div>

          <ReviewBlock title="Draft order">
            <DraftOrderList league={league} onClockMemberId={onClockMemberId} />
          </ReviewBlock>
        </div>
      </Stack>
    </Card>
  );
}
