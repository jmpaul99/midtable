"use client";

import { useRouter } from "next/navigation";
import { formatDate, formatNumber } from "@/lib/format";
import type { MatchLogRow, MatchOwnerInfo, UUID } from "@/lib/types";
import { Status } from "@/components/ui/State";
import { Muted } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";

function ownerLabel(owner: MatchOwnerInfo | null | undefined): string | null {
  return owner?.team_name?.trim() || owner?.display_name?.trim() || null;
}

function ClubRow({
  leagueId,
  teamId,
  teamName,
  owner,
}: {
  leagueId: UUID;
  teamId: UUID;
  teamName: string;
  owner?: MatchOwnerInfo | null;
}) {
  const name = ownerLabel(owner);
  return (
    <div className="min-w-0">
      <strong className="block truncate text-sm leading-snug sm:text-base">
        <TeamLink leagueId={leagueId} teamId={teamId}>
          {teamName}
        </TeamLink>
      </strong>
      {name && (
        <Muted className="mt-0.5 block truncate text-[11px] sm:text-xs">
          <ManagerLink
            leagueId={leagueId}
            managerId={owner?.member_id}
            className="font-semibold text-ink hover:text-brand"
          >
            {name}
          </ManagerLink>
        </Muted>
      )}
    </div>
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
  const router = useRouter();
  const matchHref = `/leagues/${leagueId}/matches/${m.id}`;
  const hasPoints = m.home_points != null || m.away_points != null;
  const meta = [
    m.scheduled_matchweek != null ? `MW${m.scheduled_matchweek}` : null,
    showPoolLabel && m.pool_label ? m.pool_label : null,
  ].filter(Boolean);

  return (
    <div
      role="link"
      tabIndex={0}
      onClick={() => router.push(matchHref)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          router.push(matchHref);
        }
      }}
      className={cn(
        "block min-w-0 cursor-pointer rounded-xl border border-line bg-surface-2/50 p-3 transition",
        "hover:border-brand/40 hover:bg-surface active:scale-[0.99] sm:p-3.5",
        "focus-visible:border-brand/40 focus-visible:outline-none",
      )}
    >
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
          <div className="mt-1 flex flex-col gap-1.5">
            <ClubRow
              leagueId={leagueId}
              teamId={m.home_team_id}
              teamName={m.home_team_name}
              owner={m.home_owner}
            />
            <ClubRow
              leagueId={leagueId}
              teamId={m.away_team_id}
              teamName={m.away_team_name}
              owner={m.away_owner}
            />
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="flex flex-col items-end gap-1">
            <Status value={m.status} />
            <div className="font-display text-base font-extrabold tabular-nums sm:text-lg">
              {m.home_goals ?? "—"}–{m.away_goals ?? "—"}
            </div>
            {hasPoints && (
              <Muted className="text-[11px] tabular-nums sm:text-xs">
                {formatNumber(m.home_points ?? 0)}/{formatNumber(m.away_points ?? 0)} pts
              </Muted>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
