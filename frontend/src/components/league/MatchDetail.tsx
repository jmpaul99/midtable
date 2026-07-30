"use client";

import { useMemo } from "react";
import { formatDate, formatNumber, formatScoreline, formatPeriodShort, scoringCompetitionType } from "@/lib/format";
import { scoringEventLabel } from "@/lib/scoringLabels";
import { matchDurationLabel, matchStageLabel } from "@/lib/matchStages";
import type { Json, MatchEventsResponse, MatchOwnerInfo, UUID } from "@/lib/types";
import { matchOwnerLabel } from "@/lib/types";
import { ErrorState, Loading, Status } from "@/components/ui/State";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { SurfaceListRow } from "@/components/ui/SurfaceListRow";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";
import { useApiQuery } from "@/lib/useApiQuery";
import { useLeague } from "@/components/LeagueShell";

const EVENT_ORDER = [
  "win",
  "win_et",
  "win_pk",
  "draw",
  "loss",
  "loss_et",
  "loss_pk",
  "minor_upset",
  "major_upset",
  "major_upset_draw",
] as const;

function OwnerLine({
  leagueId,
  owner,
}: {
  leagueId: UUID;
  owner?: MatchOwnerInfo | null;
}) {
  const name = matchOwnerLabel(owner);
  if (!name) return <span>—</span>;
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

function eventMetaLine(eventType: string, meta: Record<string, Json> | null | undefined) {
  if (!meta) return null;
  if (String(eventType).includes("upset")) {
    const parts = [
      meta.underdog_rank != null ? `Underdog #${meta.underdog_rank}` : null,
      meta.opponent_rank != null ? `opponent #${meta.opponent_rank}` : null,
      meta.gap != null ? `gap ${meta.gap}` : null,
    ].filter(Boolean);
    return parts.length ? parts.join(" · ") : null;
  }
  const parts = [
    meta.home_rank != null ? `Home #${meta.home_rank}` : null,
    meta.away_rank != null ? `away #${meta.away_rank}` : null,
    meta.duration && meta.duration !== "REGULAR"
      ? matchDurationLabel(String(meta.duration))
      : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

export function MatchDetail({
  leagueId,
  matchId,
  eventTypeLabels,
}: {
  leagueId: UUID;
  matchId: UUID;
  eventTypeLabels?: Record<string, string>;
}) {
  const league = useLeague();
  const competitionType = scoringCompetitionType(league.pools);
  const { data, error, loading } = useApiQuery<MatchEventsResponse>(
    `/leagues/${leagueId}/matches/${matchId}/events`,
    [leagueId, matchId],
  );

  const sortedEvents = useMemo(() => {
    const events = data?.events ?? [];
    return [...events].sort((a, b) => {
      const ai = EVENT_ORDER.indexOf(a.event_type as (typeof EVENT_ORDER)[number]);
      const bi = EVENT_ORDER.indexOf(b.event_type as (typeof EVENT_ORDER)[number]);
      const aOrder = ai === -1 ? EVENT_ORDER.length : ai;
      const bOrder = bi === -1 ? EVENT_ORDER.length : bi;
      if (aOrder !== bOrder) return aOrder - bOrder;
      return a.points === b.points
        ? (a.team_name || "").localeCompare(b.team_name || "")
        : b.points - a.points;
    });
  }, [data?.events]);

  if (error) return <ErrorState error={error} />;
  if (loading || !data) return <Loading label="Loading match" />;

  const scoreline = formatScoreline(data.home_goals, data.away_goals);
  const hasPoints = data.home_points != null || data.away_points != null;
  const homeOwner = matchOwnerLabel(data.home_owner);
  const awayOwner = matchOwnerLabel(data.away_owner);
  const meta = [
    data.scheduled_matchweek != null
      ? formatPeriodShort(data.scheduled_matchweek, competitionType)
      : null,
    data.pool_label || null,
    data.duration && data.duration !== "REGULAR" ? matchDurationLabel(data.duration) : null,
    data.stage ? matchStageLabel(data.stage) : null,
  ].filter(Boolean);

  return (
    <Stack gap="md" className="animate-in">
      <Card>
        <Stack>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <Eyebrow>Match</Eyebrow>
              <Muted className="text-xs">
                {formatDate(data.kickoff_at)}
                {meta.length > 0 ? ` · ${meta.join(" · ")}` : ""}
              </Muted>
            </div>
            <Status value={data.status} />
          </div>

          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 sm:gap-4">
            <div className="min-w-0 text-right">
              <strong className="block truncate text-base sm:text-lg">
                <TeamLink leagueId={leagueId} teamId={data.home_team_id}>
                  {data.home_team_name}
                </TeamLink>
              </strong>
              {homeOwner && (
                <Muted className="mt-0.5 truncate text-xs">
                  <OwnerLine leagueId={leagueId} owner={data.home_owner} />
                </Muted>
              )}
            </div>
            <div className="shrink-0 text-center">
              <div className="font-display text-2xl font-extrabold tabular-nums sm:text-3xl">
                {scoreline ?? "vs"}
              </div>
              {hasPoints && (
                <Muted className="mt-1 text-xs tabular-nums">
                  {formatNumber(data.home_points ?? 0)} / {formatNumber(data.away_points ?? 0)} pts
                </Muted>
              )}
            </div>
            <div className="min-w-0 text-left">
              <strong className="block truncate text-base sm:text-lg">
                <TeamLink leagueId={leagueId} teamId={data.away_team_id}>
                  {data.away_team_name}
                </TeamLink>
              </strong>
              {awayOwner && (
                <Muted className="mt-0.5 truncate text-xs">
                  <OwnerLine leagueId={leagueId} owner={data.away_owner} />
                </Muted>
              )}
            </div>
          </div>
        </Stack>
      </Card>

      <Card>
        <Stack>
          <div>
            <Eyebrow>Scoring</Eyebrow>
            <h2>Scoring events</h2>
          </div>
          {sortedEvents.length === 0 ? (
            <Muted>No scoring events for this match yet.</Muted>
          ) : (
            <ul className="flex flex-col gap-2">
              {sortedEvents.map((e) => {
                const detail = eventMetaLine(e.event_type, e.metadata);
                return (
                  <SurfaceListRow key={e.id} as="li" className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <strong className="block truncate capitalize">
                        {scoringEventLabel(e.event_type, eventTypeLabels)}
                      </strong>
                      <Muted className="mt-0.5 truncate text-xs">
                        {e.team_id ? (
                          <TeamLink leagueId={leagueId} teamId={e.team_id}>
                            {e.team_name || "Team"}
                          </TeamLink>
                        ) : (
                          e.team_name || "—"
                        )}
                        {detail ? ` · ${detail}` : ""}
                      </Muted>
                    </div>
                    <span className="shrink-0 font-display text-lg font-extrabold tabular-nums">
                      {formatNumber(e.points)}
                      <span className="ml-0.5 text-xs font-bold text-muted">pts</span>
                    </span>
                  </SurfaceListRow>
                );
              })}
            </ul>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}
