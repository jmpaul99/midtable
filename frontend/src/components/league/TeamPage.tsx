"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { formatNumber } from "@/lib/format";
import type {
  BonusAward,
  Manager,
  ScoringEventMatch,
  TeamDetail,
  UUID,
} from "@/lib/types";
import { matchOwnerLabel, opponentOptionLabel } from "@/lib/types";
import { fetchTeamFixturesPage } from "@/lib/teamFixtures";
import { usePagedTeamFixtures } from "@/lib/usePagedTeamFixtures";
import { ErrorState, Loading } from "@/components/ui/State";
import {
  Card,
  Eyebrow,
  Muted,
  Stack,
  StatGrid,
  StatTile,
} from "@/components/ui/Card";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Field";
import { useApiQuery } from "@/lib/useApiQuery";
import { TeamCrest } from "./TeamCrest";
import { TeamFixtureList } from "./TeamFixtureList";
import { TeamScoringBreakdown } from "./TeamScoringBreakdown";
import { StagePointsBreakdown } from "./StagePointsBreakdown";

const FIXTURE_SELECT_CLASS =
  "min-h-9 w-auto min-w-0 flex-1 basis-[9.5rem] rounded-lg px-2.5 py-1.5 text-sm sm:flex-none sm:basis-auto";

function FormDots({ form }: { form?: string[] }) {
  if (!form?.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {form.map((letter, i) => (
        <span
          key={`${letter}-${i}`}
          className={
            "grid size-6 place-items-center rounded-md text-[11px] font-extrabold sm:size-7 sm:text-xs " +
            (letter === "W"
              ? "bg-emerald-100 text-emerald-800"
              : letter === "D"
                ? "bg-amber-100 text-amber-800"
                : "bg-rose-100 text-rose-800")
          }
        >
          {letter}
        </span>
      ))}
    </div>
  );
}

export function TeamPage({
  leagueId,
  leagueName,
  teamId,
  members = [],
  currentManagerId,
  eventTypeLabels,
}: {
  leagueId: UUID;
  leagueName: string;
  teamId: UUID;
  members?: Manager[];
  currentManagerId?: UUID | null;
  eventTypeLabels?: Record<string, string>;
}) {
  const {
    data: team,
    error,
    loading,
  } = useApiQuery<TeamDetail>(`/leagues/${leagueId}/teams/${teamId}`, [leagueId, teamId]);
  const [opponentMemberId, setOpponentMemberId] = useState("");
  const fixtureFilterKey = opponentMemberId;

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
      fetchTeamFixturesPage(leagueId, teamId, {
        section,
        limit,
        offset,
        opponent_member_id: opponentMemberId || undefined,
      }),
    [leagueId, teamId, opponentMemberId],
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
    for (const e of team?.scoring_events || []) {
      const list = map.get(e.match_id) || [];
      list.push(e);
      map.set(e.match_id, list);
    }
    return map;
  }, [team?.scoring_events]);

  const bonusesByMatchId = useMemo(() => {
    const map = new Map<string, BonusAward[]>();
    for (const b of team?.bonuses || []) {
      if (!b.match_id) continue;
      const list = map.get(b.match_id) || [];
      list.push(b);
      map.set(b.match_id, list);
    }
    return map;
  }, [team?.bonuses]);

  if (error) return <ErrorState error={error} />;
  if (loading || !team) return <Loading label="Loading team" />;

  const s = team.stats;
  const bonuses = team.bonuses || [];
  const scoringEvents = team.scoring_events || [];
  const ownerTeamName = matchOwnerLabel(team.owner);
  const ownerPersonName = team.owner?.display_name?.trim() || "Unknown";
  // Include this club's owner so matches vs their other clubs can be filtered.
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
            { label: leagueName, href: `/leagues/${leagueId}` },
            ...(ownerTeamName
              ? [
                  {
                    label: ownerTeamName,
                    href: team.owner?.member_id
                      ? `/leagues/${leagueId}/managers/${team.owner.member_id}`
                      : undefined,
                  },
                ]
              : []),
            { label: team.name },
          ]}
        />
        <div className="flex items-start gap-2.5 sm:items-center sm:gap-3">
          <TeamCrest
            name={team.name}
            crestUrl={team.crest_url}
            size="lg"
            className="size-12 shrink-0 sm:size-14"
          />
          <div className="min-w-0 flex-1">
            <h1 className="truncate font-display text-2xl font-extrabold sm:text-3xl">
              {team.name}
            </h1>
            {s.form && s.form.length > 0 && (
              <div className="mt-2">
                <FormDots form={s.form} />
              </div>
            )}
          </div>
        </div>
        {team.owner && (
          <Muted className="mt-2 break-words text-sm">
            Owned by{" "}
            {team.owner.member_id ? (
              <Link
                href={`/leagues/${leagueId}/managers/${team.owner.member_id}`}
                className="font-semibold text-ink hover:text-brand"
              >
                {ownerPersonName}
              </Link>
            ) : (
              ownerPersonName
            )}
            {team.owner.acquired_via
              ? ` · ${team.owner.acquired_via.replaceAll("_", " ")}`
              : ""}
          </Muted>
        )}
      </div>

      <StatGrid className="lg:grid-cols-4">
        <StatTile label="Points" value={formatNumber(s.total_points)} />
        <StatTile label="PPG" value={formatNumber(s.points_per_game)} />
        <StatTile label="Games" value={s.games_played} />
        <StatTile label="Record" value={`${s.wins}-${s.draws}-${s.losses}`} />
        <StatTile
          label="Table"
          value={s.table_position != null ? `#${s.table_position}` : "—"}
        />
        <StatTile
          label="GD"
          value={
            s.goal_difference != null
              ? `${s.goal_difference > 0 ? "+" : ""}${s.goal_difference}`
              : "—"
          }
          hint={`${s.goals_for ?? 0} GF · ${s.goals_against ?? 0} GA`}
        />
        <StatTile label="Upset pts" value={formatNumber(s.upset_points)} />
        <StatTile
          label="Bonus pts"
          value={formatNumber(s.bonus_points)}
          hint={
            bonuses.length
              ? `${bonuses.length} award${bonuses.length === 1 ? "" : "s"}`
              : "None yet"
          }
        />
      </StatGrid>

      <TeamScoringBreakdown
        leagueId={leagueId}
        events={scoringEvents}
        bonuses={bonuses}
        bonusPoints={s.bonus_points}
        eventPointsByType={s.event_points_by_type}
        eventCountsByType={s.event_counts_by_type}
        eventTypeLabels={eventTypeLabels}
      />

      {s.points_by_stage && Object.keys(s.points_by_stage).length > 1 && (
        <Card className="min-w-0 overflow-hidden">
          <Stack>
            <StagePointsBreakdown pointsByStage={s.points_by_stage} />
          </Stack>
        </Card>
      )}

      {(s.home || s.away) && (
        <Card className="min-w-0 overflow-hidden">
          <Stack>
            <h2>Home vs away</h2>
            <div className="grid grid-cols-2 gap-2 sm:gap-3">
              {(["home", "away"] as const).map((key) => {
                const v = s[key];
                if (!v) return null;
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
                      {formatNumber(v.points)} pts
                      <span className="block sm:inline">
                        <span className="hidden sm:inline"> · </span>
                        {formatNumber(v.points_per_game)} PPG
                      </span>
                    </Muted>
                  </div>
                );
              })}
            </div>
          </Stack>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2 lg:justify-center">
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
          disabled={!opponentMemberId}
          onClick={() => setOpponentMemberId("")}
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
                eventsByMatchId={eventsByMatchId}
                bonusesByMatchId={bonusesByMatchId}
                eventTypeLabels={eventTypeLabels}
                loading={recentFixtures.loading}
                hasMore={recentFixtures.hasMore}
                loadingMore={recentFixtures.loadingMore}
                onShowMore={recentFixtures.showMore}
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
                loading={upcomingFixtures.loading}
                hasMore={upcomingFixtures.hasMore}
                loadingMore={upcomingFixtures.loadingMore}
                onShowMore={upcomingFixtures.showMore}
              />
            )}
          </Stack>
        </Card>
      </div>
    </Stack>
  );
}
