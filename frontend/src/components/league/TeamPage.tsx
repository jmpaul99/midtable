"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/format";
import type {
  BonusAward,
  ScoringEventMatch,
  TeamDetail,
  TeamFixture,
  UUID,
} from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import {
  Card,
  Eyebrow,
  Muted,
  Stack,
  StatGrid,
  StatTile,
} from "@/components/ui/Card";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { TeamCrest } from "./TeamCrest";
import { TeamLink } from "./TeamLink";
import { TeamScoringBreakdown } from "./TeamScoringBreakdown";
import { StagePointsBreakdown } from "./StagePointsBreakdown";

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

function scoreline(m: TeamFixture) {
  return m.is_home
    ? `${m.home_goals ?? "—"}–${m.away_goals ?? "—"}`
    : `${m.away_goals ?? "—"}–${m.home_goals ?? "—"}`;
}

function FixtureList({
  leagueId,
  fixtures,
  empty,
  showPoints,
  eventsByMatchId,
  bonusesByMatchId,
  eventTypeLabels,
}: {
  leagueId: UUID;
  fixtures: TeamFixture[];
  empty: string;
  showPoints?: boolean;
  eventsByMatchId?: Map<string, ScoringEventMatch[]>;
  bonusesByMatchId?: Map<string, BonusAward[]>;
  eventTypeLabels?: Record<string, string>;
}) {
  if (!fixtures.length) return <Empty title={empty} />;
  return (
    <ul className="flex flex-col gap-2">
      {fixtures.map((m) => {
        const matchEvents = eventsByMatchId?.get(m.id) || [];
        const matchBonuses = bonusesByMatchId?.get(m.id) || [];
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
        const showBreakdown = showPoints && parts.length > 1;
        const ownerName =
          m.opponent_owner?.team_name?.trim() ||
          m.opponent_owner?.display_name?.trim() ||
          null;

        return (
          <li key={m.id}>
            <Link
              href={`/leagues/${leagueId}/matches/${m.id}`}
              className="block min-w-0 rounded-xl border border-line bg-surface-2/50 p-3 transition hover:border-brand/40 hover:bg-surface active:scale-[0.99] sm:p-3.5"
            >
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
                    {m.is_home ? "vs" : "@"}{" "}
                    <TeamLink leagueId={leagueId} teamId={m.opponent_id}>
                      {m.opponent_name}
                    </TeamLink>
                  </strong>
                  {ownerName && (
                    <Muted className="mt-0.5 block truncate text-[11px] sm:text-xs">
                      {m.opponent_owner?.member_id ? (
                        <Link
                          href={`/leagues/${leagueId}/managers/${m.opponent_owner.member_id}`}
                          className="font-semibold text-ink hover:text-brand"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {ownerName}
                        </Link>
                      ) : (
                        ownerName
                      )}
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
                  {showPoints ? (
                    <>
                      <div className="font-display text-base font-extrabold tabular-nums sm:text-lg">
                        {displayPoints != null ? formatNumber(displayPoints) : "—"}
                        <span className="ml-0.5 text-xs font-bold text-muted sm:text-sm">
                          pts
                        </span>
                      </div>
                      <Muted className="mt-1 text-[11px] tabular-nums sm:text-xs">
                        {scoreline(m)}
                      </Muted>
                    </>
                  ) : null}
                </div>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function TeamPage({
  leagueId,
  leagueName,
  teamId,
  eventTypeLabels,
}: {
  leagueId: UUID;
  leagueName: string;
  teamId: UUID;
  eventTypeLabels?: Record<string, string>;
}) {
  const [team, setTeam] = useState<TeamDetail>();
  const [error, setError] = useState("");

  useEffect(() => {
    setTeam(undefined);
    setError("");
    api<TeamDetail>(`/leagues/${leagueId}/teams/${teamId}`)
      .then(setTeam)
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId, teamId]);

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
  if (!team) return <Loading label="Loading team" />;

  const s = team.stats;
  const bonuses = team.bonuses || [];
  const scoringEvents = team.scoring_events || [];
  const ownerTeamName =
    team.owner?.team_name?.trim() ||
    team.owner?.display_name?.trim() ||
    null;

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
                {team.owner.display_name || "Unknown"}
              </Link>
            ) : (
              team.owner.display_name || "Unknown"
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

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card className="min-w-0 overflow-hidden">
          <Stack>
            <h2>Recent results</h2>
            <FixtureList
              leagueId={leagueId}
              fixtures={team.recent_matches.slice(0, 5)}
              empty="No finished matches yet"
              showPoints
              eventsByMatchId={eventsByMatchId}
              bonusesByMatchId={bonusesByMatchId}
              eventTypeLabels={eventTypeLabels}
            />
          </Stack>
        </Card>
        <Card className="min-w-0 overflow-hidden">
          <Stack>
            <h2>Upcoming fixtures</h2>
            <FixtureList
              leagueId={leagueId}
              fixtures={team.upcoming_matches.slice(0, 5)}
              empty="No upcoming fixtures"
            />
          </Stack>
        </Card>
      </div>
    </Stack>
  );
}
