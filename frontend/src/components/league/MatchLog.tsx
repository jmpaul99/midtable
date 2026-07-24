"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/format";
import type { MatchLogRow, UUID } from "@/lib/types";
import { Empty, ErrorState, Loading, Status } from "@/components/ui/State";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { TeamLink } from "./TeamLink";

export function MatchLog({
  leagueId,
  limit,
  compact = false,
}: {
  leagueId: UUID;
  limit?: number;
  compact?: boolean;
}) {
  const [matches, setMatches] = useState<MatchLogRow[]>();
  const [error, setError] = useState("");

  useEffect(() => {
    api<MatchLogRow[]>(`/leagues/${leagueId}/match-log`)
      .then(setMatches)
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  if (error) return <ErrorState error={error} />;
  if (!matches) return <Loading label="Loading match log" />;
  if (!matches.length) return <Empty title="No matches synced yet" />;

  const rows = typeof limit === "number" ? matches.slice(0, limit) : matches;

  const list = (
    <ul className="flex flex-col gap-2">
      {rows.map((m) => (
        <li key={m.id}>
          <Link
            href={`/leagues/${leagueId}/matches/${m.id}`}
            className="block min-w-0 rounded-xl border border-line bg-surface-2/50 p-3 transition hover:border-brand/40 hover:bg-surface active:scale-[0.99] sm:p-3.5"
          >
            <div className="flex items-start justify-between gap-2 sm:gap-3">
              <div className="min-w-0 flex-1">
                <Muted className="text-[11px] sm:text-xs">{formatDate(m.kickoff_at)}</Muted>
                <strong className="mt-1 block break-words text-sm leading-snug sm:text-base">
                  <TeamLink leagueId={leagueId} teamId={m.home_team_id}>
                    {m.home_team_name}
                  </TeamLink>
                  <span className="text-muted"> vs </span>
                  <TeamLink leagueId={leagueId} teamId={m.away_team_id}>
                    {m.away_team_name}
                  </TeamLink>
                </strong>
              </div>
              <div className="shrink-0 text-right">
                <div className="font-display text-base font-extrabold tabular-nums sm:text-lg">
                  {m.home_goals ?? "—"}–{m.away_goals ?? "—"}
                </div>
                <div className="mt-1 flex flex-col items-end gap-1">
                  <Status value={m.status} />
                  {(m.home_points != null || m.away_points != null) && (
                    <Muted className="text-[11px] tabular-nums sm:text-xs">
                      {formatNumber(m.home_points ?? 0)}/
                      {formatNumber(m.away_points ?? 0)} pts
                    </Muted>
                  )}
                </div>
              </div>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );

  if (compact) return list;

  return (
    <Card className="animate-in min-w-0 overflow-hidden">
      <Stack>
        <div>
          <Eyebrow>Fixtures</Eyebrow>
          <h2>Match log</h2>
        </div>
        {list}
      </Stack>
    </Card>
  );
}
