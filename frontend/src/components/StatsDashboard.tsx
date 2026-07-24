"use client";

import { useEffect, useState } from "react";
import { api, errorMessage, formatNumber } from "@/lib/api";
import type { AnalyticsRow, UUID } from "@/lib/types";
import { Empty, ErrorState, Loading } from "./State";

export function StatsDashboard({ leagueId }: { leagueId: UUID }) {
  const [teams, setTeams] = useState<AnalyticsRow[]>();
  const [members, setMembers] = useState<AnalyticsRow[]>();
  const [weeks, setWeeks] = useState<AnalyticsRow[]>();
  const [upsets, setUpsets] = useState<AnalyticsRow[]>();
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all(
      (["teams", "members", "matchweeks", "upsets"] as const).map((key) =>
        api<AnalyticsRow[]>(`/leagues/${leagueId}/analytics/${key}`),
      ),
    )
      .then(([a, b, c, d]) => {
        setTeams(a);
        setMembers(b);
        setWeeks(c);
        setUpsets(d);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  if (error) return <ErrorState error={error} />;
  if (!teams || !members || !weeks || !upsets) return <Loading label="Crunching stats" />;

  const max = Math.max(1, ...members.map((r) => Number(r.total_points || 0)));

  return (
    <div className="stack">
      <div className="grid grid-3">
        <section className="panel">
          <p className="eyebrow">Scored teams</p>
          <div className="metric">{teams.length}</div>
        </section>
        <section className="panel">
          <p className="eyebrow">Matchweeks</p>
          <div className="metric">{new Set(weeks.map((w) => w.matchday)).size}</div>
        </section>
        <section className="panel">
          <p className="eyebrow">Upsets</p>
          <div className="metric">{upsets.length}</div>
        </section>
      </div>

      <div className="grid grid-2">
        <section className="panel">
          <h2>Manager points &amp; PPG</h2>
          {!members.length ? (
            <Empty title="No member stats" />
          ) : (
            <div className="bar-chart">
              {members.map((r, i) => (
                <div className="bar-row" key={i}>
                  <span>{String(r.display_name)}</span>
                  <div className="bar">
                    <i
                      style={{
                        width: `${Math.max(
                          0,
                          Math.min(100, (Number(r.total_points || 0) / max) * 100),
                        )}%`,
                      }}
                    />
                  </div>
                  <strong>{formatNumber(Number(r.ppg || 0))}</strong>
                </div>
              ))}
            </div>
          )}
        </section>
        <section className="panel">
          <h2>Team performance</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Team</th>
                  <th>Points</th>
                  <th>PPG</th>
                </tr>
              </thead>
              <tbody>
                {teams.slice(0, 12).map((r, i) => (
                  <tr key={i}>
                    <td>{String(r.team_name)}</td>
                    <td>{formatNumber(Number(r.points || 0))}</td>
                    <td>{formatNumber(Number(r.ppg || 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className="panel">
        <h2>Matchweek &amp; cumulative</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>MW</th>
                <th>Manager</th>
                <th>Week</th>
                <th>Cumulative</th>
                <th>Upset</th>
              </tr>
            </thead>
            <tbody>
              {weeks.map((r, i) => (
                <tr key={i}>
                  <td>{String(r.matchday)}</td>
                  <td>{String(r.display_name)}</td>
                  <td>{formatNumber(Number(r.points || 0))}</td>
                  <td>{formatNumber(Number(r.cumulative_points || 0))}</td>
                  <td>{formatNumber(Number(r.upset_points || 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <h2>Upset highlights</h2>
        {upsets.length ? (
          <div className="grid grid-3">
            {upsets.slice(0, 9).map((r, i) => (
              <div className="panel inset" key={i}>
                <strong>{String(r.team_name)}</strong>
                <div className="metric">+{formatNumber(Number(r.points || 0))}</div>
                <small className="muted">MW {String(r.matchday)}</small>
              </div>
            ))}
          </div>
        ) : (
          <Empty title="No upsets recorded" />
        )}
      </section>
    </div>
  );
}
