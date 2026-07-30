"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { DraftPick, League, Manager } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import {
  buildBoardCells,
  cellKey,
  orderedDraftMembers,
  totalRounds as rosterTotalRounds,
} from "@/lib/draftBoard";
import { cn } from "@/lib/cn";
import { formatCountdownDuration } from "@/lib/format";
import { Card, Eyebrow, Muted, RankBadge, Stack } from "@/components/ui/Card";
import { Empty } from "@/components/ui/State";
import { TeamCrest } from "./TeamCrest";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";

const ROUND_COL = "sticky left-0 z-20 w-10 sm:w-12";
/** Opaque brand tint — translucent fills bleed through sticky headers. */
const ON_CLOCK_BG =
  "bg-[color-mix(in_srgb,var(--color-brand)_14%,var(--color-surface))]";
/** Slightly stronger column tint so the viewer’s roster reads as “yours”. */
const YOUR_COL_BG =
  "bg-[color-mix(in_srgb,var(--color-brand)_9%,var(--color-surface))]";
const YOUR_COL_CELL_BG =
  "bg-[color-mix(in_srgb,var(--color-brand)_7%,var(--color-surface-2))]";
const YOUR_COL_EDGE_X =
  "shadow-[inset_3px_0_0_0_var(--color-brand),inset_-3px_0_0_0_var(--color-brand)]";
const YOUR_COL_EDGE_TOP =
  "shadow-[inset_3px_0_0_0_var(--color-brand),inset_-3px_0_0_0_var(--color-brand),inset_0_3px_0_0_var(--color-brand)]";
const YOUR_COL_EDGE_BOTTOM =
  "shadow-[inset_3px_0_0_0_var(--color-brand),inset_-3px_0_0_0_var(--color-brand),inset_0_-3px_0_0_var(--color-brand)]";

export function DraftRoundBoard({
  league,
  picks,
  currentPickNumber,
  currentRound,
  onClockMemberId,
  crestByTeamId,
  yourTurn = false,
  deadlineAt = null,
}: {
  league: League;
  picks: DraftPick[];
  currentPickNumber: number;
  currentRound: number;
  onClockMemberId?: string | null;
  crestByTeamId: Map<string, string | null>;
  yourTurn?: boolean;
  deadlineAt?: string | null;
}) {
  const yourMemberId = league.current_member_id;
  const ordered = useMemo(() => orderedDraftMembers(league), [league]);
  const rosterRounds = useMemo(() => rosterTotalRounds(league.pools), [league.pools]);
  const { rounds, cells, onClockKey } = useMemo(
    () =>
      buildBoardCells({
        orderedMembers: ordered,
        picks,
        draftStyle: league.draft_style || "linear",
        currentPickNumber,
        currentRound,
        onClockMemberId,
        totalRounds: rosterRounds,
      }),
    [
      ordered,
      picks,
      league.draft_style,
      currentPickNumber,
      currentRound,
      onClockMemberId,
      rosterRounds,
    ],
  );

  const onClockMember = useMemo(
    () => ordered.find((m) => m.id === onClockMemberId) ?? null,
    [ordered, onClockMemberId],
  );

  const onClockRef = useRef<HTMLTableCellElement | null>(null);
  const scrollKey = `${currentPickNumber}:${onClockMemberId ?? ""}:${onClockKey ?? ""}`;

  useEffect(() => {
    const el = onClockRef.current;
    if (!el) return;
    el.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [scrollKey]);

  if (!ordered.length) {
    return (
      <Card
        className={cn(
          "min-w-0 max-w-full overflow-hidden",
          yourTurn && "draft-on-clock-pulse",
        )}
      >
        <Stack>
          <h2>Draft board</h2>
          <Empty title="No managers in draft order" />
        </Stack>
      </Card>
    );
  }

  return (
    <Card
      className={cn(
        "min-w-0 max-w-full overflow-hidden",
        yourTurn && "draft-on-clock-pulse",
      )}
    >
      <Stack className="min-w-0">
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <Eyebrow>
              {league.draft_style === "snake" ? "Snake" : "Linear"} · {ordered.length}{" "}
              managers
            </Eyebrow>
            <h2>Draft board</h2>
          </div>
          {(onClockMember || yourTurn) && (
            <OnClockStatus
              leagueId={league.id}
              onClockMember={onClockMember}
              yourTurn={yourTurn}
              currentPickNumber={currentPickNumber}
              currentRound={currentRound}
              deadlineAt={deadlineAt}
            />
          )}
        </div>
        <div
          className="max-h-[min(75dvh,42rem)] max-w-full overflow-auto overscroll-x-contain lg:max-h-[min(80dvh,48rem)] [scrollbar-width:thin]"
          role="region"
          aria-label="Draft board by round and manager"
        >
          <table
            className="w-full table-fixed border-separate border-spacing-0 text-left min-w-[max(100%,calc(2.5rem+var(--managers)*5.75rem))] sm:min-w-[max(100%,calc(3rem+var(--managers)*7rem))]"
            style={{ ["--managers" as string]: ordered.length }}
          >
            <colgroup>
              <col className="w-10 sm:w-12" />
              {ordered.map((m) => (
                <col key={m.id} />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th
                  scope="col"
                  className={cn(
                    ROUND_COL,
                    "top-0 z-30 border-b border-r border-line bg-surface px-1 py-2 text-center text-[10px] font-bold uppercase tracking-wide text-muted sm:text-xs",
                  )}
                >
                  Rd
                </th>
                {ordered.map((m, index) => {
                  const isYou = Boolean(yourMemberId && m.id === yourMemberId);
                  const isOnClock = onClockMemberId === m.id;
                  return (
                    <th
                      key={m.id}
                      scope="col"
                      className={cn(
                        "sticky top-0 z-10 border-b border-line px-1.5 py-2 sm:px-2",
                        isOnClock ? ON_CLOCK_BG : isYou ? YOUR_COL_BG : "bg-surface",
                        isYou && YOUR_COL_EDGE_TOP,
                      )}
                    >
                      <div className="flex min-w-0 flex-col items-center gap-1">
                        <RankBadge
                          value={m.draft_slot ?? index + 1}
                          className={
                            isYou || isOnClock
                              ? "bg-[color-mix(in_srgb,var(--color-brand)_22%,var(--color-surface))] text-brand"
                              : undefined
                          }
                        />
                        <ManagerLink leagueId={league.id} managerId={m.id}>
                          <span
                            className={cn(
                              "block max-w-full truncate text-center text-[11px] font-bold leading-tight sm:text-xs",
                              (isYou || isOnClock) && "text-brand",
                            )}
                            title={managerLabel(m)}
                          >
                            {managerLabel(m)}
                          </span>
                        </ManagerLink>
                        {isYou ? (
                          <span className="rounded-md bg-brand/15 px-1.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide text-brand">
                            You
                          </span>
                        ) : null}
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: rounds }, (_, i) => i + 1).map((round) => (
                <tr key={round}>
                  <th
                    scope="row"
                    className={cn(
                      ROUND_COL,
                      "border-b border-r border-line bg-surface px-1 py-1.5 text-center text-xs font-bold tabular-nums text-muted sm:text-sm",
                    )}
                  >
                    {round}
                  </th>
                  {ordered.map((m) => {
                    const key = cellKey(round, m.id);
                    const cell = cells.get(key) ?? { kind: "empty" as const, onClock: false };
                    const isOnClock = cell.onClock;
                    const isYou = Boolean(yourMemberId && m.id === yourMemberId);
                    const isLastRound = round === rounds;
                    return (
                      <td
                        key={m.id}
                        ref={isOnClock ? onClockRef : undefined}
                        className={cn(
                          "border-b border-line px-1 py-1.5 align-top sm:px-1.5",
                          isOnClock
                            ? cn(ON_CLOCK_BG, "ring-2 ring-inset ring-brand/50")
                            : isYou
                              ? YOUR_COL_CELL_BG
                              : "bg-surface-2",
                          isYou && (isLastRound ? YOUR_COL_EDGE_BOTTOM : YOUR_COL_EDGE_X),
                        )}
                      >
                        {cell.kind === "picked" ? (
                          <PickedCell
                            leagueId={league.id}
                            pick={cell.pick}
                            crestByTeamId={crestByTeamId}
                            yours={isYou}
                          />
                        ) : (
                          <div
                            className={cn(
                              "flex min-h-[4.75rem] items-center justify-center rounded-md border border-dashed px-1 py-1.5 sm:min-h-[5.25rem]",
                              isOnClock
                                ? "border-brand bg-surface"
                                : isYou
                                  ? "border-brand/35 bg-surface"
                                  : "border-line bg-surface",
                            )}
                          >
                            {isOnClock ? (
                              <span className="px-1 text-center text-[10px] font-bold uppercase leading-snug tracking-wide text-brand sm:text-xs">
                                On the clock
                              </span>
                            ) : (
                              <span className="sr-only">Empty</span>
                            )}
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Muted className="text-xs sm:hidden">Swipe sideways to see all managers.</Muted>
      </Stack>
    </Card>
  );
}

function OnClockStatus({
  leagueId,
  onClockMember,
  yourTurn,
  currentPickNumber,
  currentRound,
  deadlineAt,
}: {
  leagueId: string;
  onClockMember: Manager | null;
  yourTurn: boolean;
  currentPickNumber: number;
  currentRound: number;
  deadlineAt?: string | null;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!deadlineAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [deadlineAt]);

  const remaining = deadlineAt ? new Date(deadlineAt).getTime() - now : null;
  const expired = remaining != null && remaining <= 0;
  const urgent = remaining != null && (expired || remaining < 15_000);
  const showTimer = Boolean(deadlineAt);

  const who = yourTurn
    ? "You"
    : onClockMember
      ? managerLabel(onClockMember)
      : "—";

  return (
    <div
      className={cn(
        "flex min-w-0 shrink-0 flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-xl border px-3 py-2",
        yourTurn
          ? "border-brand/40 bg-[color-mix(in_srgb,var(--color-brand)_10%,var(--color-surface))]"
          : "border-line bg-surface-2",
      )}
      aria-live="polite"
    >
      <span className="min-w-0 truncate text-sm font-bold text-ink">
        {onClockMember && !yourTurn ? (
          <ManagerLink leagueId={leagueId} managerId={onClockMember.id}>
            {who}
          </ManagerLink>
        ) : (
          who
        )}
      </span>
      <Muted className="text-xs font-semibold tabular-nums">
        Rd {currentRound} · Pick {currentPickNumber}
      </Muted>
      {showTimer ? (
        <span
          className={cn(
            "font-mono text-base font-extrabold tabular-nums tracking-tight",
            urgent ? "text-danger" : "text-brand",
          )}
        >
          {expired ? "0:00" : formatCountdownDuration(remaining!)}
        </span>
      ) : null}
    </div>
  );
}

function PickedCell({
  leagueId,
  pick,
  crestByTeamId,
  yours = false,
}: {
  leagueId: string;
  pick: DraftPick;
  crestByTeamId: Map<string, string | null>;
  yours?: boolean;
}) {
  const name = String(pick.team_name || pick.team_id || "Team");
  const crest =
    pick.crest_url ?? (pick.team_id ? crestByTeamId.get(pick.team_id) : null) ?? null;
  return (
    <div
      className={cn(
        "flex min-h-[4.75rem] min-w-0 flex-col items-center justify-center gap-1 rounded-md border bg-surface px-1.5 py-1.5 sm:min-h-[5.25rem]",
        yours ? "border-brand/40 shadow-sm" : "border-line/80",
      )}
    >
      <TeamCrest name={name} crestUrl={crest} size="sm" className="shrink-0 sm:size-9" />
      <span
        className={cn(
          "max-w-full text-center text-[10px] font-bold leading-snug sm:text-xs",
          yours && "text-brand",
        )}
        title={name}
      >
        {pick.team_id ? (
          <TeamLink leagueId={leagueId} teamId={pick.team_id}>
            <span className="line-clamp-2 break-words">{name}</span>
          </TeamLink>
        ) : (
          <span className="line-clamp-2 break-words">{name}</span>
        )}
      </span>
    </div>
  );
}
