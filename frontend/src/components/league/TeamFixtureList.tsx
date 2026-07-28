"use client";

import { formatDate, formatNumber, formatTeamOrientedScoreline } from "@/lib/format";
import type { BonusAward, ScoringEventMatch, TeamFixture, UUID } from "@/lib/types";
import { matchOwnerLabel } from "@/lib/types";
import { Empty, Loading, Status } from "@/components/ui/State";
import { Muted } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";
import { MatchRowShell } from "./MatchRowShell";

const EVENT_LABELS: Record<string, string> = {
  win: "Win",
  win_et: "Win (ET)",
  win_pk: "Win (PK)",
  draw: "Draw",
  loss: "Loss",
  loss_et: "Loss (ET)",
  loss_pk: "Loss (PK)",
  minor_upset: "Minor upset",
  major_upset: "Major upset",
  major_upset_draw: "Major upset draw",
};

function eventLabel(key: string, labels?: Record<string, string>) {
  return labels?.[key] || EVENT_LABELS[key] || key.replaceAll("_", " ");
}

function focusTeamId(m: TeamFixture): UUID {
  return m.is_home ? m.home_team_id : m.away_team_id;
}

function focusTeamName(m: TeamFixture): string {
  return m.is_home ? m.home_team_name : m.away_team_name;
}

export function TeamFixtureList({
  leagueId,
  fixtures,
  empty,
  showPoints,
  showFocusClub,
  ownedTeamIds,
  eventsByMatchId,
  bonusesByMatchId,
  eventTypeLabels,
  loading,
  hasMore,
  loadingMore,
  onShowMore,
}: {
  leagueId: UUID;
  fixtures: TeamFixture[];
  empty: string;
  showPoints?: boolean;
  showFocusClub?: boolean;
  /** When set with showFocusClub, intra-roster derbies keep both clubs' events. */
  ownedTeamIds?: ReadonlySet<UUID>;
  eventsByMatchId?: Map<string, ScoringEventMatch[]>;
  bonusesByMatchId?: Map<string, BonusAward[]>;
  eventTypeLabels?: Record<string, string>;
  loading?: boolean;
  hasMore?: boolean;
  loadingMore?: boolean;
  onShowMore?: () => void;
}) {
  if (loading) return <Loading label="Loading matches" />;
  if (!fixtures.length) return <Empty title={empty} />;

  return (
    <>
      <ul className="flex flex-col gap-2">
        {fixtures.map((m) => {
          const focusId = focusTeamId(m);
          const intraRoster =
            Boolean(ownedTeamIds?.has(focusId) && ownedTeamIds.has(m.opponent_id));
          let matchEvents = eventsByMatchId?.get(m.id) || [];
          let matchBonuses = bonusesByMatchId?.get(m.id) || [];
          if (showFocusClub && !intraRoster) {
            matchEvents = matchEvents.filter(
              (e) => e.is_home === m.is_home && e.opponent_id === m.opponent_id,
            );
            matchBonuses = matchBonuses.filter(
              (b) => !b.team_id || b.team_id === focusId,
            );
          }
          const parts: { label: string; points: number }[] = [];
          for (const e of matchEvents) {
            parts.push({
              label: eventLabel(e.event_type, eventTypeLabels),
              points: e.points,
            });
          }
          for (const b of matchBonuses) {
            parts.push({
              label: b.bonus_type_label || b.bonus_type,
              points: b.points,
            });
          }
          const bonusPts = matchBonuses.reduce((sum, b) => sum + b.points, 0);
          const displayPoints =
            m.points != null || matchBonuses.length
              ? (m.points ?? 0) + bonusPts
              : null;
          const scoreline = formatTeamOrientedScoreline(m);
          const showBreakdown = showPoints && parts.length > 1;
          const ownerName = matchOwnerLabel(m.opponent_owner);
          const matchHref = `/leagues/${leagueId}/matches/${m.id}`;

          return (
            <li key={`${m.id}-${focusId}`}>
              <MatchRowShell href={matchHref}>
                <div className="flex items-start justify-between gap-2 sm:gap-3">
                  <div className="min-w-0 flex-1">
                    <Muted className="text-[11px] leading-snug sm:text-xs">
                      <span className="block sm:inline">{formatDate(m.kickoff_at)}</span>
                      <span className="hidden sm:inline">
                        {m.scheduled_matchweek != null ? ` · MW${m.scheduled_matchweek}` : ""}
                        {m.is_home ? " · Home" : " · Away"}
                      </span>
                      <span className="mt-0.5 block sm:hidden">
                        {[
                          m.scheduled_matchweek != null ? `MW${m.scheduled_matchweek}` : null,
                          m.is_home ? "Home" : "Away",
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </Muted>
                    <strong className="mt-1 block truncate text-sm leading-snug sm:text-base">
                      {showFocusClub ? (
                        <>
                          <TeamLink leagueId={leagueId} teamId={focusId}>
                            {focusTeamName(m)}
                          </TeamLink>{" "}
                          {m.is_home ? "vs" : "@"}{" "}
                          <TeamLink leagueId={leagueId} teamId={m.opponent_id}>
                            {m.opponent_name}
                          </TeamLink>
                        </>
                      ) : (
                        <>
                          {m.is_home ? "vs" : "@"}{" "}
                          <TeamLink leagueId={leagueId} teamId={m.opponent_id}>
                            {m.opponent_name}
                          </TeamLink>
                        </>
                      )}
                    </strong>
                    {ownerName && (
                      <Muted className="mt-0.5 block truncate text-[11px] sm:text-xs">
                        <ManagerLink
                          leagueId={leagueId}
                          managerId={m.opponent_owner?.member_id}
                          className="font-semibold text-ink hover:text-brand"
                        >
                          {ownerName}
                        </ManagerLink>
                      </Muted>
                    )}
                    {showBreakdown && (
                      <Muted className="mt-1 block text-[11px] tabular-nums sm:text-xs">
                        {parts
                          .map((p) => `${p.label} ${formatNumber(p.points)}`)
                          .join(" · ")}
                      </Muted>
                    )}
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="flex flex-col items-end gap-1">
                      <Status value={m.status} />
                      {showPoints ? (
                        <>
                          <div className="font-display text-base font-extrabold tabular-nums sm:text-lg">
                            {displayPoints != null ? formatNumber(displayPoints) : "—"}
                            <span className="ml-0.5 text-xs font-bold text-muted sm:text-sm">
                              pts
                            </span>
                          </div>
                          {scoreline && (
                            <Muted className="text-[11px] tabular-nums sm:text-xs">
                              {scoreline}
                            </Muted>
                          )}
                        </>
                      ) : null}
                    </div>
                  </div>
                </div>
              </MatchRowShell>
            </li>
          );
        })}
      </ul>
      {hasMore && onShowMore && (
        <div className="flex justify-start">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={loadingMore}
            onClick={onShowMore}
          >
            {loadingMore ? "Loading…" : "Show more"}
          </Button>
        </div>
      )}
    </>
  );
}
