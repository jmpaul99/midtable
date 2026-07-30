"use client";

import { useCallback, useMemo, useState } from "react";
import { useApiQuery } from "@/lib/useApiQuery";
import { formatNumber, scoringCompetitionType, formatPeriodNoun, formatPeriodShort } from "@/lib/format";
import { scoringEventLabel } from "@/lib/scoringLabels";
import { humanizeKey } from "@/components/settings/types";
import type {
  BonusAward,
  Manager,
  ManagerDetail,
  ManagerHighlights,
  ScoringEventMatch,
  UUID,
  VenueSplitRow,
} from "@/lib/types";
import { managerLabel, opponentOptionLabel } from "@/lib/types";
import { fetchMemberFixturesPage } from "@/lib/teamFixtures";
import { usePagedTeamFixtures } from "@/lib/usePagedTeamFixtures";
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
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Field";
import {
  compareRosterClubs,
  effectiveRosterClubOrder,
  type RosterClubOrder,
} from "@/lib/rosterClubOrder";
import { useLeague } from "@/components/LeagueShell";
import { TeamCrest } from "./TeamCrest";
import { TeamFixtureList } from "./TeamFixtureList";
import { TeamLink } from "./TeamLink";
import { TeamNameEditor } from "./TeamNameEditor";
import { BonusAwardsPanel } from "./BonusAwardsPanel";

const FIXTURE_SELECT_CLASS =
  "min-h-9 w-auto min-w-0 flex-1 basis-[9.5rem] rounded-lg px-2.5 py-1.5 text-sm sm:flex-none sm:basis-auto";

export function ManagerPage({
  leagueId,
  managerId,
  currentManagerId,
  members = [],
  onTeamNameSaved,
  leagueStatus,
  rosterClubOrder = "draft",
  eventTypeLabels,
  bonusesConfigured = false,
}: {
  leagueId: UUID;
  managerId: UUID;
  currentManagerId?: UUID | null;
  members?: Manager[];
  onTeamNameSaved?: () => void;
  leagueStatus?: string;
  rosterClubOrder?: RosterClubOrder;
  eventTypeLabels?: Record<string, string>;
  /** League has at least one bonus type defined. */
  bonusesConfigured?: boolean;
}) {
  const league = useLeague();
  const competitionType = scoringCompetitionType(league.pools);
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
  const [clubId, setClubId] = useState("");
  const [opponentMemberId, setOpponentMemberId] = useState("");
  const fixtureFilterKey = `${clubId}|${opponentMemberId}`;

  const fetchFixturePage = useCallback(
    ({
      section,
      limit,
      offset,
    }: {
      section: "recent" | "upcoming";
      limit: number;
      offset: number;
    }) =>
      fetchMemberFixturesPage(leagueId, managerId, {
        section,
        limit,
        offset,
        club_id: clubId || undefined,
        opponent_member_id: opponentMemberId || undefined,
      }),
    [leagueId, managerId, clubId, opponentMemberId],
  );

  const recentFixtures = usePagedTeamFixtures({
    section: "recent",
    filterKey: fixtureFilterKey,
    fetchPage: fetchFixturePage,
  });
  const upcomingFixtures = usePagedTeamFixtures({
    section: "upcoming",
    filterKey: fixtureFilterKey,
    fetchPage: fetchFixturePage,
  });

  const eventsByMatchId = useMemo(() => {
    const map = new Map<string, ScoringEventMatch[]>();
    for (const e of detail?.scoring_events || []) {
      const list = map.get(e.match_id) || [];
      list.push(e);
      map.set(e.match_id, list);
    }
    return map;
  }, [detail?.scoring_events]);

  const bonusesByMatchId = useMemo(() => {
    const map = new Map<string, BonusAward[]>();
    for (const b of detail?.bonuses || []) {
      if (!b.match_id) continue;
      const list = map.get(b.match_id) || [];
      list.push(b);
      map.set(b.match_id, list);
    }
    return map;
  }, [detail?.bonuses]);

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
  const ownedTeamIds = new Set(clubs.map((c) => c.team_id));
  // Include this manager so intra-roster derbies can be filtered as Opponent.
  // Current manager "(You)" sorts first.
  const opponentOptions = [...members].sort((a, b) => {
    const aYou = Boolean(currentManagerId && a.id === currentManagerId);
    const bYou = Boolean(currentManagerId && b.id === currentManagerId);
    if (aYou !== bYou) return aYou ? -1 : 1;
    return opponentOptionLabel(a, currentManagerId).localeCompare(
      opponentOptionLabel(b, currentManagerId),
      undefined,
      { sensitivity: "base" },
    );
  });

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
        <StatTile
          label="Games"
          value={`${s.games_played}/${s.games_total ?? 0}`}
        />
        <StatTile label="Record" value={`${s.wins}-${s.draws}-${s.losses}`} />
        <StatTile label="Upset pts" value={formatNumber(s.upset_points)} />
        {(bonusesConfigured || bonuses.length > 0 || s.bonus_points > 0) && (
          <StatTile
            label="Bonus pts"
            value={formatNumber(s.bonus_points)}
            hint={
              bonuses.length
                ? `${bonuses.length} award${bonuses.length === 1 ? "" : "s"} below`
                : undefined
            }
          />
        )}
      </StatGrid>

      {(bonusesConfigured || bonuses.length > 0 || s.bonus_points > 0) && (
        <BonusAwardsPanel
          leagueId={leagueId}
          bonuses={bonuses}
          totalPoints={s.bonus_points}
          showTeam
        />
      )}

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
                    <Eyebrow>
                      Best{" "}
                      {formatPeriodNoun(
                        highlights.period_kind === "matchweek" ? "LEAGUE" : "CUP",
                        { capitalize: false },
                      )}
                    </Eyebrow>
                    <div className="font-display text-xl font-extrabold tabular-nums sm:text-2xl">
                      {highlights.best_matchweek.label ||
                        (highlights.best_matchweek.scheduled_matchweek != null
                          ? formatPeriodShort(
                              highlights.best_matchweek.scheduled_matchweek,
                              competitionType,
                            )
                          : "—")}
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
                    <div className="font-display text-lg font-extrabold sm:text-xl">
                      {scoringEventLabel(
                        highlights.biggest_upset.event_type || "",
                        eventTypeLabels,
                      )}
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
                  <span className="min-w-0 truncate">
                    {scoringEventLabel(key, eventTypeLabels)}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted">
                    {s.event_counts_by_type?.[key] ?? 0} · {formatNumber(pts)} pts
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
                                : club.acquired_via
                                  ? humanizeKey(club.acquired_via)
                                  : null,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                          <span className="mt-0.5 block tabular-nums sm:mt-0 sm:inline">
                            <span className="hidden sm:inline"> · </span>
                            {club.games_played}/{club.games_total ?? 0} GP ·{" "}
                            {formatNumber(club.points_per_game)} PPG · {share}% of
                            total points
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

      <div className="flex flex-wrap items-center gap-2 lg:justify-center">
        <Select
          aria-label="Club"
          className={FIXTURE_SELECT_CLASS}
          value={clubId}
          onChange={(e) => setClubId(e.target.value)}
        >
          <option value="">All clubs</option>
          {clubs.map((c) => (
            <option key={c.team_id} value={c.team_id}>
              {c.team_name}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Opponent"
          className={FIXTURE_SELECT_CLASS}
          value={opponentMemberId}
          onChange={(e) => setOpponentMemberId(e.target.value)}
        >
          <option value="">All opponents</option>
          {opponentOptions.map((m) => (
            <option key={m.id} value={m.id}>
              {opponentOptionLabel(m, currentManagerId)}
            </option>
          ))}
        </Select>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={!clubId && !opponentMemberId}
          onClick={() => {
            setClubId("");
            setOpponentMemberId("");
          }}
        >
          Clear filters
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card className="min-w-0 overflow-hidden">
          <Stack>
            <h2>Recent results</h2>
            {recentFixtures.error && (
              <ErrorState error={recentFixtures.error} />
            )}
            {(!recentFixtures.error || recentFixtures.items.length > 0) && (
              <TeamFixtureList
                leagueId={leagueId}
                fixtures={recentFixtures.items}
                empty="No finished matches yet"
                showPoints
                showFocusClub
                ownedTeamIds={ownedTeamIds}
                eventsByMatchId={eventsByMatchId}
                bonusesByMatchId={bonusesByMatchId}
                eventTypeLabels={eventTypeLabels}
                loading={recentFixtures.loading}
                hasMore={recentFixtures.hasMore}
                loadingMore={recentFixtures.loadingMore}
                onShowMore={recentFixtures.showMore}
                competitionType={competitionType}
              />
            )}
          </Stack>
        </Card>
        <Card className="min-w-0 overflow-hidden">
          <Stack>
            <h2>Upcoming fixtures</h2>
            {upcomingFixtures.error && (
              <ErrorState error={upcomingFixtures.error} />
            )}
            {(!upcomingFixtures.error || upcomingFixtures.items.length > 0) && (
              <TeamFixtureList
                leagueId={leagueId}
                fixtures={upcomingFixtures.items}
                empty="No upcoming fixtures"
                showFocusClub
                ownedTeamIds={ownedTeamIds}
                loading={upcomingFixtures.loading}
                hasMore={upcomingFixtures.hasMore}
                loadingMore={upcomingFixtures.loadingMore}
                onShowMore={upcomingFixtures.showMore}
                competitionType={competitionType}
              />
            )}
          </Stack>
        </Card>
      </div>
    </Stack>
  );
}
