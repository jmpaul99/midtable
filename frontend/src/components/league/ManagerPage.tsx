"use client";

import { useApiQuery } from "@/lib/useApiQuery";
import { formatNumber } from "@/lib/format";
import type { ManagerDetail, ManagerHighlights, UUID, VenueSplitRow } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import {
  Card,
  Eyebrow,
  Muted,
  RankBadge,
  Stack,
  StatGrid,
  StatTile,
} from "@/components/ui/Card";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import {
  compareRosterClubs,
  effectiveRosterClubOrder,
  type RosterClubOrder,
} from "@/lib/rosterClubOrder";
import { TeamCrest } from "./TeamCrest";
import { TeamLink } from "./TeamLink";
import { TeamNameEditor } from "./TeamNameEditor";
import { BonusAwardsPanel } from "./BonusAwardsPanel";

export function ManagerPage({
  leagueId,
  managerId,
  currentManagerId,
  onTeamNameSaved,
  leagueStatus,
  rosterClubOrder = "draft",
  eventTypeLabels,
}: {
  leagueId: UUID;
  managerId: UUID;
  currentManagerId?: UUID | null;
  onTeamNameSaved?: () => void;
  leagueStatus?: string;
  rosterClubOrder?: RosterClubOrder;
  eventTypeLabels?: Record<string, string>;
}) {
  const clubOrder = effectiveRosterClubOrder(leagueStatus, rosterClubOrder);
  const detailQ = useApiQuery<ManagerDetail>(
    `/leagues/${leagueId}/members/${managerId}`,
    [leagueId, managerId],
  );
  const highlightsQ = useApiQuery<ManagerHighlights>(
    `/leagues/${leagueId}/stats/highlights?member_id=${managerId}`,
    [leagueId, managerId],
  );
  const splitsQ = useApiQuery<VenueSplitRow[]>(
    `/leagues/${leagueId}/stats/splits?member_id=${managerId}`,
    [leagueId, managerId],
  );
  const detail = detailQ.data ?? undefined;
  const highlights = highlightsQ.data ?? undefined;
  const splits = splitsQ.data ?? undefined;
  const error = detailQ.error || highlightsQ.error || splitsQ.error || "";
  const reloadDetail = detailQ.reload;

  if (error) return <ErrorState error={error} />;
  if (!detail) return <Loading label="Loading roster" />;

  const s = detail.stats;
  const teamName = managerLabel(
    { team_name: detail.team_name, display_name: detail.display_name },
    "Roster",
  );
  const ownerName = detail.display_name?.trim() || null;
  const eventEntries = Object.entries(s.event_points_by_type || {}).sort(
    (a, b) => b[1] - a[1],
  );
  const totalClubPts = detail.clubs.reduce((n, c) => n + c.points, 0) || 1;
  const managerSplit = splits?.[0];
  const isMine = Boolean(currentManagerId && currentManagerId === managerId);
  const bonuses = detail.bonuses || [];
  const clubs = [...detail.clubs].sort((a, b) => compareRosterClubs(a, b, clubOrder));

  return (
    <Stack gap="md" className="animate-in">
      <div className="min-w-0">
        <Breadcrumbs
          items={[
            { label: "Rosters", href: `/leagues/${leagueId}/roster` },
            { label: teamName },
          ]}
        />
        <div className="flex items-start gap-2.5 sm:items-center sm:gap-3">
          {detail.rank != null && (
            <RankBadge
              value={detail.rank}
              first={detail.rank === 1}
              className="mt-1 sm:mt-0"
            />
          )}
          <div className="min-w-0 flex-1">
            <TeamNameEditor
              leagueId={leagueId}
              memberId={managerId}
              teamName={detail.team_name?.trim() || ""}
              displayName={ownerName}
              canEdit={isMine}
              titleAs="h1"
              titleClassName="truncate font-display text-2xl font-extrabold sm:text-3xl"
              titleContent={teamName}
              onSaved={() => {
                onTeamNameSaved?.();
                reloadDetail();
              }}
            />
          </div>
        </div>
      </div>

      <StatGrid>
        <StatTile label="Points" value={formatNumber(s.total_points)} />
        <StatTile label="PPG" value={formatNumber(s.points_per_game)} />
        <StatTile label="Games" value={s.games_played} />
        <StatTile label="Record" value={`${s.wins}-${s.draws}-${s.losses}`} />
        <StatTile label="Upset pts" value={formatNumber(s.upset_points)} />
        <StatTile
          label="Bonus pts"
          value={formatNumber(s.bonus_points)}
          hint={
            bonuses.length
              ? `${bonuses.length} award${bonuses.length === 1 ? "" : "s"} below`
              : undefined
          }
        />
      </StatGrid>

      <BonusAwardsPanel
        leagueId={leagueId}
        bonuses={bonuses}
        totalPoints={s.bonus_points}
        showTeam
      />

      {highlights &&
        (highlights.best_matchweek ||
          highlights.biggest_upset ||
          highlights.top_club) && (
          <Card className="min-w-0 overflow-hidden">
            <Stack>
              <h2>Highlights</h2>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 sm:gap-3">
                {highlights.best_matchweek && (
                  <div className="min-w-0 rounded-xl border border-line bg-surface-2/40 p-3">
                    <Eyebrow>Best week</Eyebrow>
                    <div className="font-display text-xl font-extrabold tabular-nums sm:text-2xl">
                      MW{highlights.best_matchweek.scheduled_matchweek}
                    </div>
                    <Muted className="tabular-nums">
                      {formatNumber(highlights.best_matchweek.points)} pts
                    </Muted>
                  </div>
                )}
                {highlights.top_club && (
                  <div className="min-w-0 rounded-xl border border-line bg-surface-2/40 p-3">
                    <Eyebrow>Top club</Eyebrow>
                    <div className="truncate font-display text-lg font-extrabold sm:text-xl">
                      <TeamLink leagueId={leagueId} teamId={highlights.top_club.team_id}>
                        {highlights.top_club.team_name}
                      </TeamLink>
                    </div>
                    <Muted className="tabular-nums">
                      {formatNumber(highlights.top_club.points)} pts
                    </Muted>
                  </div>
                )}
                {highlights.biggest_upset && (
                  <div className="min-w-0 rounded-xl border border-line bg-surface-2/40 p-3">
                    <Eyebrow>Biggest upset</Eyebrow>
                    <div className="font-display text-lg font-extrabold capitalize sm:text-xl">
                      {eventTypeLabels?.[highlights.biggest_upset.event_type || ""] ||
                        (highlights.biggest_upset.event_type || "").replaceAll("_", " ")}
                    </div>
                    <Muted className="break-words text-sm tabular-nums">
                      {highlights.biggest_upset.gap != null
                        ? `Gap ${highlights.biggest_upset.gap} · `
                        : ""}
                      {formatNumber(highlights.biggest_upset.points)} pts
                      {highlights.biggest_upset.opponent_name
                        ? ` vs ${highlights.biggest_upset.opponent_name}`
                        : ""}
                    </Muted>
                  </div>
                )}
              </div>
            </Stack>
          </Card>
        )}

      {managerSplit && (
        <Card className="min-w-0 overflow-hidden">
          <Stack>
            <h2>Home vs away</h2>
            <div className="grid grid-cols-2 gap-2 sm:gap-3">
              {(["home", "away"] as const).map((key) => {
                const v = managerSplit[key];
                return (
                  <div
                    key={key}
                    className="min-w-0 rounded-xl border border-line bg-surface-2/40 p-3"
                  >
                    <Eyebrow>{key}</Eyebrow>
                    <div className="font-display text-xl font-extrabold tabular-nums sm:text-2xl">
                      {v.wins}-{v.draws}-{v.losses}
                    </div>
                    <Muted className="mt-1 text-xs tabular-nums sm:text-sm">
                      <span className="block sm:inline">
                        {formatNumber(v.points)} pts
                      </span>
                      <span className="hidden sm:inline"> · </span>
                      <span className="block sm:inline">
                        {formatNumber(v.points_per_game)} PPG · {v.games_played} GP
                      </span>
                    </Muted>
                  </div>
                );
              })}
            </div>
          </Stack>
        </Card>
      )}

      {eventEntries.length > 0 && (
        <Card className="min-w-0 overflow-hidden">
          <Stack>
            <h2>Scoring breakdown</h2>
            <ul className="flex flex-col gap-2">
              {eventEntries.map(([key, pts]) => (
                <li
                  key={key}
                  className="flex min-w-0 items-center justify-between gap-2 rounded-xl border border-line bg-surface-2/40 px-3 py-2.5 text-sm"
                >
                  <span className="min-w-0 truncate capitalize">
                    {key.replaceAll("_", " ")}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted">
                    {s.event_counts_by_type?.[key] ?? 0}× · {formatNumber(pts)}
                  </span>
                </li>
              ))}
            </ul>
          </Stack>
        </Card>
      )}

      <Card className="min-w-0 overflow-hidden">
        <Stack>
          <h2>Clubs</h2>
          {!clubs.length ? (
            <Empty title="No clubs on this roster yet" />
          ) : (
            <ul className="flex flex-col gap-2">
              {clubs.map((club) => {
                const share = Math.round((club.points / totalClubPts) * 100);
                return (
                  <li
                    key={club.team_id}
                    className="min-w-0 rounded-xl border border-line bg-surface-2/50 p-2.5 sm:p-3"
                  >
                    <div className="flex items-start gap-2.5 sm:items-center sm:gap-3">
                      <TeamCrest
                        name={club.team_name}
                        crestUrl={club.crest_url}
                        size="md"
                        className="mt-0.5 shrink-0 sm:mt-0"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <strong className="min-w-0 truncate text-sm sm:text-base">
                            <TeamLink leagueId={leagueId} teamId={club.team_id}>
                              {club.team_name}
                            </TeamLink>
                          </strong>
                          <div className="shrink-0 text-right leading-none">
                            <div className="font-display text-lg font-extrabold tabular-nums sm:text-xl">
                              {formatNumber(club.points)}
                            </div>
                            <Muted className="text-[11px] sm:text-xs">pts</Muted>
                          </div>
                        </div>
                        <Muted className="mt-0.5 text-xs sm:text-sm">
                          <span className="block truncate sm:inline">
                            {[
                              club.pool_name,
                              club.draft_pick_number != null
                                ? `Pick #${club.draft_pick_number}`
                                : club.acquired_via?.replaceAll("_", " "),
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                          <span className="mt-0.5 block tabular-nums sm:mt-0 sm:inline">
                            <span className="hidden sm:inline"> · </span>
                            {club.games_played} GP · {formatNumber(club.points_per_game)} PPG ·{" "}
                            {share}%
                          </span>
                        </Muted>
                      </div>
                    </div>
                    <div className="mt-2 h-1 overflow-hidden rounded-full bg-line sm:h-1.5">
                      <div
                        className="h-full rounded-full bg-brand/80"
                        style={{ width: `${share}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}
