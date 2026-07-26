"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { formatDate, formatNumber } from "@/lib/format";
import type { BonusAward, UUID } from "@/lib/types";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { TeamCrest } from "./TeamCrest";
import { TeamLink } from "./TeamLink";
import { cn } from "@/lib/cn";

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

export function BonusAwardsPanel({
  leagueId,
  bonuses,
  totalPoints,
  showTeam = false,
}: {
  leagueId: UUID;
  bonuses: BonusAward[];
  totalPoints: number;
  /** Show club crest/name (manager page — awards span multiple clubs). */
  showTeam?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  if (!bonuses.length && !totalPoints) return null;

  return (
    <Card className="min-w-0 overflow-hidden p-0 sm:p-0">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-12 w-full items-center justify-between gap-3 px-4 py-3.5 text-left transition hover:bg-surface-2/60 sm:px-5 sm:py-4"
      >
        <div className="min-w-0">
          <Eyebrow className="mb-0.5">Bonus points</Eyebrow>
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="font-display text-xl font-extrabold tabular-nums sm:text-2xl">
              {formatNumber(totalPoints)}
            </span>
            <Muted className="text-xs sm:text-sm">
              {bonuses.length === 0
                ? "No awards yet"
                : `${bonuses.length} award${bonuses.length === 1 ? "" : "s"} · tap to ${open ? "hide" : "view"}`}
            </Muted>
          </div>
        </div>
        <Chevron open={open} />
      </button>

      {open && (
        <div id={panelId} className="border-t border-line px-4 pb-4 pt-3 sm:px-5 sm:pb-5">
          {!bonuses.length ? (
            <Muted className="text-sm">No individual bonus awards on record.</Muted>
          ) : (
            <Stack gap="sm">
              <ul className="flex flex-col gap-2">
                {bonuses.map((b) => {
                  const isManager = b.target === "manager" || (!b.team_id && !b.match_id);
                  return (
                  <li
                    key={b.id}
                    className="min-w-0 rounded-xl border border-line bg-surface-2/50 p-3"
                  >
                    <div className="flex items-start gap-2.5 sm:gap-3">
                      {showTeam && !isManager && (
                        <TeamCrest
                          name={b.team_name}
                          crestUrl={b.crest_url}
                          size="md"
                          className="mt-0.5 shrink-0"
                        />
                      )}
                      {showTeam && isManager && (
                        <div
                          className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-surface text-[10px] font-bold uppercase tracking-wide text-muted"
                          aria-hidden
                        >
                          Mgr
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <strong className="block truncate text-sm sm:text-base">
                              {b.bonus_type_label || b.bonus_type}
                            </strong>
                            {showTeam && isManager && (
                              <Muted className="mt-0.5 truncate text-xs sm:text-sm">
                                Manager award
                              </Muted>
                            )}
                            {showTeam && !isManager && b.team_id && b.team_name && (
                              <Muted className="mt-0.5 truncate text-xs sm:text-sm">
                                <TeamLink leagueId={leagueId} teamId={b.team_id}>
                                  {b.team_name}
                                </TeamLink>
                              </Muted>
                            )}
                            {b.match_label && (
                              <Muted className="mt-0.5 truncate text-xs sm:text-sm">
                                {b.match_id ? (
                                  <Link
                                    href={`/leagues/${leagueId}/matches/${b.match_id}`}
                                    className="underline-offset-2 hover:underline"
                                  >
                                    {b.match_label}
                                  </Link>
                                ) : (
                                  b.match_label
                                )}
                              </Muted>
                            )}
                          </div>
                          <div className="shrink-0 text-right leading-none">
                            <div className="font-display text-lg font-extrabold tabular-nums">
                              {formatNumber(b.points)}
                            </div>
                            <Muted className="text-[11px]">pts</Muted>
                          </div>
                        </div>
                        {b.reason && (
                          <p className="mt-1.5 break-words text-sm text-muted">{b.reason}</p>
                        )}
                        {b.awarded_at && (
                          <Muted className="mt-1 text-[11px] sm:text-xs">
                            Awarded {formatDate(b.awarded_at)}
                          </Muted>
                        )}
                      </div>
                    </div>
                  </li>
                  );
                })}
              </ul>
            </Stack>
          )}
        </div>
      )}
    </Card>
  );
}
