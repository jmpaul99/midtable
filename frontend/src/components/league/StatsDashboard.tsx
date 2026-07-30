"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { formatNumber, formatPeriodNoun, formatPeriodShort, scoringCompetitionType } from "@/lib/format";
import { scoringEventLabel } from "@/lib/scoringLabels";
import type { League, MatchweekRow, PpgRow, UpsetRow, UUID } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import { Button } from "@/components/ui/Button";
import { Card, Muted, Stack, StatTile } from "@/components/ui/Card";
import { useApiQuery } from "@/lib/useApiQuery";
import { MatchLog } from "./MatchLog";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";

const TEAM_PPG_PAGE_SIZE = 10;

function statsManagerName(displayName: string | null | undefined, memberId: string | null | undefined) {
  return managerLabel(
    { display_name: displayName ?? null, team_name: null },
    String(memberId || "Manager"),
  );
}

export function StatsDashboard({
  leagueId,
  eventTypeLabels,
  league,
}: {
  leagueId: UUID;
  eventTypeLabels?: Record<string, string>;
  league?: League;
}) {
  const competitionType = scoringCompetitionType(league?.pools);
  const periodNoun = formatPeriodNoun(competitionType, { plural: true });
  const ppgQ = useApiQuery<PpgRow[]>(`/leagues/${leagueId}/stats/points-per-game`, [leagueId]);
  const weeksQ = useApiQuery<MatchweekRow[]>(`/leagues/${leagueId}/stats/matchweeks`, [leagueId]);
  const upsetsQ = useApiQuery<UpsetRow[]>(`/leagues/${leagueId}/stats/upsets`, [leagueId]);
  const ppg = ppgQ.data ?? undefined;
  const weeks = weeksQ.data ?? undefined;
  const upsets = upsetsQ.data ?? undefined;
  const error = ppgQ.error || weeksQ.error || upsetsQ.error || "";
  const [teamPpgPage, setTeamPpgPage] = useState(1);

  const cumulative = useMemo(() => {
    if (!weeks) return [];
    const byMember = new Map<
      string,
      { name: string; points: number; series: Array<{ key: string; label: string; total: number }> }
    >();
    const order = new Map<string, number>();
    let ord = 0;
    for (const row of weeks) {
      const key = row.period_key || String(row.scheduled_matchweek ?? "");
      if (key && !order.has(key)) order.set(key, ord++);
    }
    const sorted = [...weeks].sort((a, b) => {
      const ak = a.period_key || String(a.scheduled_matchweek ?? "");
      const bk = b.period_key || String(b.scheduled_matchweek ?? "");
      return (order.get(ak) ?? 0) - (order.get(bk) ?? 0);
    });
    for (const row of sorted) {
      const mid = String(row.member_id || "");
      const prev = byMember.get(mid) || {
        name: statsManagerName(row.display_name, row.member_id),
        points: 0,
        series: [],
      };
      prev.points += Number(row.points || 0);
      const key = row.period_key || String(row.scheduled_matchweek ?? "");
      const label =
        row.label ||
        (row.scheduled_matchweek != null
          ? formatPeriodShort(row.scheduled_matchweek, competitionType)
          : key);
      prev.series.push({ key, label, total: prev.points });
      byMember.set(mid, prev);
    }
    return [...byMember.entries()].map(([id, v]) => ({ id, ...v }));
  }, [weeks, competitionType]);

  const teamPpgSorted = useMemo(() => {
    if (!ppg) return [];
    return [...ppg].sort(
      (a, b) => Number(b.points_per_game || 0) - Number(a.points_per_game || 0),
    );
  }, [ppg]);

  const teamPpgTotalPages = Math.max(1, Math.ceil(teamPpgSorted.length / TEAM_PPG_PAGE_SIZE) || 1);
  const teamPpgPageClamped = Math.min(teamPpgPage, teamPpgTotalPages);
  const teamPpgPageRows = teamPpgSorted.slice(
    (teamPpgPageClamped - 1) * TEAM_PPG_PAGE_SIZE,
    teamPpgPageClamped * TEAM_PPG_PAGE_SIZE,
  );
  const showTeamPpgPager = teamPpgSorted.length > TEAM_PPG_PAGE_SIZE;

  if (error) return <ErrorState error={error} />;
  if (!ppg || !weeks || !upsets) return <Loading label="Crunching stats" />;

  const byMember = new Map<string, { name: string; points: number; games: number }>();
  for (const row of ppg) {
    const mid = String(row.member_id || "");
    const prev = byMember.get(mid) || {
      name: statsManagerName(row.display_name, row.member_id),
      points: 0,
      games: 0,
    };
    prev.points += Number(row.points || 0);
    prev.games += Number(row.games_played || 0);
    byMember.set(mid, prev);
  }
  const members = [...byMember.entries()].map(([id, v]) => ({
    id,
    ...v,
    ppg: v.games ? v.points / v.games : 0,
  }));
  const max = Math.max(1, ...members.map((r) => r.points));
  const cumMax = Math.max(1, ...cumulative.map((c) => c.points));
  const periodCount = new Set(
    weeks.map((w) => w.period_key || String(w.scheduled_matchweek ?? "")),
  ).size;

  return (
    <Stack gap="md" className="animate-in">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 sm:gap-3">
        <StatTile label="Teams" value={ppg.length} />
        <StatTile label={periodNoun} value={periodCount} />
        <StatTile
          label="Upsets"
          value={upsets.reduce((n, u) => n + Number(u.count || u.upset_count || 0), 0)}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card className="min-w-0 overflow-hidden">
          <h2 className="mb-3 text-lg sm:mb-4 sm:text-xl">Manager points &amp; PPG</h2>
          {!members.length ? (
            <Empty title="No manager stats" />
          ) : (
            <Stack gap="sm">
              {members.map((r) => (
                <div
                  key={r.id}
                  className="min-w-0 rounded-xl border border-line bg-surface-2/40 p-3"
                >
                  <div className="mb-2 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-2">
                    <ManagerLink
                      leagueId={leagueId}
                      managerId={r.id || null}
                      className="min-w-0 truncate font-bold"
                    >
                      {r.name}
                    </ManagerLink>
                    <span className="shrink-0 text-sm tabular-nums text-muted">
                      {formatNumber(r.points)} pts · {formatNumber(r.ppg)} ppg
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-line sm:h-2">
                    <div
                      className="h-full rounded-full bg-brand transition-all duration-500"
                      style={{ width: `${(r.points / max) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </Stack>
          )}
        </Card>

        <Card className="min-w-0 overflow-hidden">
          <h2 className="mb-3 text-lg sm:mb-4 sm:text-xl">Team points per game</h2>
          {!teamPpgSorted.length ? (
            <Empty title="No team stats" />
          ) : (
            <Stack gap="sm">
              <ul className="flex flex-col gap-2">
                {teamPpgPageRows.map((r, i) => (
                  <li
                    key={r.team_id ?? `${r.team_name}-${i}`}
                    className="flex min-w-0 flex-col gap-1 rounded-xl border border-line bg-surface-2/40 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-3 sm:py-3"
                  >
                    <strong className="min-w-0 truncate text-sm">
                      {r.team_id ? (
                        <TeamLink leagueId={leagueId} teamId={String(r.team_id)}>
                          {String(r.team_name || r.team_id)}
                        </TeamLink>
                      ) : (
                        String(r.team_name || r.team_id)
                      )}
                    </strong>
                    <span className="shrink-0 text-xs tabular-nums text-muted sm:text-sm">
                      {formatNumber(Number(r.points || 0))} · {Number(r.games_played || 0)} GP ·{" "}
                      {formatNumber(Number(r.points_per_game || 0))} PPG
                    </span>
                  </li>
                ))}
              </ul>
              {showTeamPpgPager && (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <Muted className="text-sm">
                    Page {teamPpgPageClamped} of {teamPpgTotalPages}
                  </Muted>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={teamPpgPageClamped <= 1}
                      onClick={() => setTeamPpgPage(teamPpgPageClamped - 1)}
                    >
                      Previous
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={teamPpgPageClamped >= teamPpgTotalPages}
                      onClick={() => setTeamPpgPage(teamPpgPageClamped + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </Stack>
          )}
        </Card>
      </div>

      <Card className="min-w-0 overflow-hidden">
        <Stack>
          <h2 className="text-lg sm:text-xl">Cumulative points by {periodNoun.toLowerCase()}</h2>
          {!cumulative.length ? (
            <Empty title={`No ${periodNoun.toLowerCase()} series yet`} />
          ) : (
            <Stack gap="sm">
              {cumulative.map((m) => (
                <div
                  key={m.id}
                  className="min-w-0 rounded-xl border border-line bg-surface-2/40 p-3"
                >
                  <div className="mb-1 flex flex-col gap-0.5 sm:flex-row sm:items-center sm:justify-between sm:gap-2">
                    <ManagerLink
                      leagueId={leagueId}
                      managerId={m.id || null}
                      className="min-w-0 truncate font-bold"
                    >
                      {m.name}
                    </ManagerLink>
                    <span className="shrink-0 text-sm tabular-nums text-muted">
                      {formatNumber(m.points)} total
                    </span>
                  </div>
                  <div className="-mx-1 mb-2 overflow-x-auto px-1">
                    <Muted className="whitespace-nowrap text-[11px] sm:text-xs">
                      {m.series.map((s) => `${s.label}:${formatNumber(s.total)}`).join(" · ")}
                    </Muted>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-line sm:h-2">
                    <div
                      className="h-full rounded-full bg-brand transition-all duration-500"
                      style={{ width: `${(m.points / cumMax) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </Stack>
          )}
        </Stack>
      </Card>

      <Card className="min-w-0 overflow-hidden">
        <Stack>
          <h2 className="text-lg sm:text-xl">Upset stats</h2>
          {!upsets.length ? (
            <Empty title="No upsets recorded" />
          ) : (
            <ul className="flex flex-col gap-2">
              {upsets.map((u, i) => {
                const byType = u.by_type || {};
                const typeBits = Object.entries(byType)
                  .sort((a, b) => b[1] - a[1])
                  .map(
                    ([k, v]) =>
                      `${scoringEventLabel(k, eventTypeLabels)} ${formatNumber(v)}`,
                  );
                return (
                  <li
                    key={i}
                    className="min-w-0 rounded-xl border border-line bg-surface-2/40 px-3 py-3"
                  >
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
                      <ManagerLink
                        leagueId={leagueId}
                        managerId={u.member_id ? String(u.member_id) : null}
                        className="min-w-0 truncate font-bold"
                      >
                        {statsManagerName(u.display_name, u.member_id)}
                      </ManagerLink>
                      <span className="shrink-0 text-sm tabular-nums text-muted">
                        {Number(u.count || u.upset_count || 0)} ·{" "}
                        {formatNumber(Number(u.points || u.upset_points || 0))} pts
                      </span>
                    </div>
                    {typeBits.length > 0 && (
                      <Muted className="mt-1 break-words text-xs">
                        {typeBits.join(" · ")}
                      </Muted>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Stack>
      </Card>

      <Card className="min-w-0 overflow-hidden">
        <Stack>
          <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between sm:gap-3">
            <h2 className="text-lg sm:text-xl">Recent match log</h2>
            <Link
              href={`/leagues/${leagueId}/matches`}
              className="text-sm font-bold text-brand hover:underline"
            >
              View all matches
            </Link>
          </div>
          <MatchLog leagueId={leagueId} league={league} limit={10} compact section="results" />
        </Stack>
      </Card>
    </Stack>
  );
}
