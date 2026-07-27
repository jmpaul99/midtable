"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, errorMessage, formatNumber } from "@/lib/api";
import type { MatchweekRow, PpgRow, UpsetRow, UUID } from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import { Card, Muted, Stack, StatTile } from "@/components/ui/Card";
import { MatchLog } from "./MatchLog";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";

export function StatsDashboard({ leagueId }: { leagueId: UUID }) {
  const [ppg, setPpg] = useState<PpgRow[]>();
  const [weeks, setWeeks] = useState<MatchweekRow[]>();
  const [upsets, setUpsets] = useState<UpsetRow[]>();
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api<PpgRow[]>(`/leagues/${leagueId}/stats/points-per-game`),
      api<MatchweekRow[]>(`/leagues/${leagueId}/stats/matchweeks`),
      api<UpsetRow[]>(`/leagues/${leagueId}/stats/upsets`),
    ])
      .then(([a, c, d]) => {
        setPpg(a);
        setWeeks(c);
        setUpsets(d);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  const cumulative = useMemo(() => {
    if (!weeks) return [];
    const byMember = new Map<
      string,
      { name: string; points: number; series: Array<{ mw: number; total: number }> }
    >();
    const sorted = [...weeks].sort(
      (a, b) => Number(a.scheduled_matchweek || 0) - Number(b.scheduled_matchweek || 0),
    );
    for (const row of sorted) {
      const mid = String(row.member_id || "");
      const prev = byMember.get(mid) || {
        name: String(row.display_name || row.member_id || "Manager"),
        points: 0,
        series: [],
      };
      prev.points += Number(row.points || 0);
      prev.series.push({ mw: Number(row.scheduled_matchweek || 0), total: prev.points });
      byMember.set(mid, prev);
    }
    return [...byMember.entries()].map(([id, v]) => ({ id, ...v }));
  }, [weeks]);

  if (error) return <ErrorState error={error} />;
  if (!ppg || !weeks || !upsets) return <Loading label="Crunching stats" />;

  const byMember = new Map<string, { name: string; points: number; games: number }>();
  for (const row of ppg) {
    const mid = String(row.member_id || "");
    const prev = byMember.get(mid) || {
      name: String(row.display_name || row.member_id || "Manager"),
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

  return (
    <Stack gap="md" className="animate-in">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 sm:gap-3">
        <StatTile label="Teams" value={ppg.length} />
        <StatTile
          label="Weeks"
          value={new Set(weeks.map((w) => w.scheduled_matchweek)).size}
        />
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
          {!ppg.length ? (
            <Empty title="No team stats" />
          ) : (
            <ul className="flex flex-col gap-2">
              {ppg.map((r, i) => (
                <li
                  key={i}
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
          )}
        </Card>
      </div>

      <Card className="min-w-0 overflow-hidden">
        <Stack>
          <h2 className="text-lg sm:text-xl">Cumulative points by matchweek</h2>
          {!cumulative.length ? (
            <Empty title="No matchweek series yet" />
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
                      {m.series.map((s) => `MW${s.mw}:${formatNumber(s.total)}`).join(" · ")}
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
                  .map(([k, v]) => `${k.replaceAll("_", " ")} ${formatNumber(v)}`);
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
                        {String(u.display_name || u.member_id)}
                      </ManagerLink>
                      <span className="shrink-0 text-sm tabular-nums text-muted">
                        {Number(u.count || u.upset_count || 0)} ·{" "}
                        {formatNumber(Number(u.points || u.upset_points || 0))} pts
                      </span>
                    </div>
                    {typeBits.length > 0 && (
                      <Muted className="mt-1 break-words text-xs capitalize">
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
          <MatchLog leagueId={leagueId} limit={10} compact section="results" />
        </Stack>
      </Card>
    </Stack>
  );
}
