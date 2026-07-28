"use client";

import { formatDate, formatNumber, formatScoreline } from "@/lib/format";
import type { MatchLogRow, MatchOwnerInfo, UUID } from "@/lib/types";
import { matchOwnerLabel } from "@/lib/types";
import { Status } from "@/components/ui/State";
import { Muted } from "@/components/ui/Card";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";
import { MatchRowShell } from "./MatchRowShell";

function OwnerLink({
  leagueId,
  owner,
}: {
  leagueId: UUID;
  owner?: MatchOwnerInfo | null;
}) {
  const name = matchOwnerLabel(owner);
  if (!name) return null;
  return (
    <ManagerLink
      leagueId={leagueId}
      managerId={owner?.member_id}
      className="font-semibold text-ink hover:text-brand"
    >
      {name}
    </ManagerLink>
  );
}

export function MatchLogCard({
  leagueId,
  match: m,
  showPoolLabel = false,
}: {
  leagueId: UUID;
  match: MatchLogRow;
  showPoolLabel?: boolean;
}) {
  const hasPoints = m.home_points != null || m.away_points != null;
  const scoreline = formatScoreline(m.home_goals, m.away_goals);
  const homeOwner = matchOwnerLabel(m.home_owner);
  const awayOwner = matchOwnerLabel(m.away_owner);
  const meta = [
    m.scheduled_matchweek != null ? `MW${m.scheduled_matchweek}` : null,
    showPoolLabel && m.pool_label ? m.pool_label : null,
  ].filter(Boolean);

  return (
    <MatchRowShell href={`/leagues/${leagueId}/matches/${m.id}`}>
      <div className="flex items-start justify-between gap-2 sm:gap-3">
        <div className="min-w-0 flex-1">
          <Muted className="text-[11px] leading-snug sm:text-xs">
            <span className="block sm:inline">{formatDate(m.kickoff_at)}</span>
            {meta.length > 0 && (
              <>
                <span className="hidden sm:inline"> · {meta.join(" · ")}</span>
                <span className="mt-0.5 block sm:hidden">{meta.join(" · ")}</span>
              </>
            )}
          </Muted>
          <strong className="mt-1 block truncate text-sm leading-snug sm:text-base">
            <TeamLink leagueId={leagueId} teamId={m.home_team_id}>
              {m.home_team_name}
            </TeamLink>{" "}
            vs{" "}
            <TeamLink leagueId={leagueId} teamId={m.away_team_id}>
              {m.away_team_name}
            </TeamLink>
          </strong>
          {(homeOwner || awayOwner) && (
            <Muted className="mt-0.5 block truncate text-[11px] sm:text-xs">
              {homeOwner ? <OwnerLink leagueId={leagueId} owner={m.home_owner} /> : "—"}
              {" vs "}
              {awayOwner ? <OwnerLink leagueId={leagueId} owner={m.away_owner} /> : "—"}
            </Muted>
          )}
        </div>
        <div className="shrink-0 text-right">
          <div className="flex flex-col items-end gap-1">
            <Status value={m.status} />
            {scoreline && (
              <div className="font-display text-base font-extrabold tabular-nums sm:text-lg">
                {scoreline}
              </div>
            )}
            {hasPoints && (
              <Muted className="text-[11px] tabular-nums sm:text-xs">
                {formatNumber(m.home_points ?? 0)}/{formatNumber(m.away_points ?? 0)} pts
              </Muted>
            )}
          </div>
        </div>
      </div>
    </MatchRowShell>
  );
}
