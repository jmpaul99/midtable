"use client";

import { useEffect, useState } from "react";
import { api, errorMessage, formatNumber } from "@/lib/api";
import type { League, StandingsResponse } from "@/lib/types";
import { Empty, ErrorState, Loading, Status } from "./State";

function uniquePhases(league: League) {
  return league.phases.filter(
    (phase, index, all) => all.findIndex((item) => item.key === phase.key) === index,
  );
}

function rungLabel(r: {
  metric: string;
  event_types?: string[];
  bonus_type_keys?: string[];
  direction: string;
  value: string | number;
}) {
  const selector = r.event_types?.length
    ? ` (${r.event_types.join(", ")})`
    : r.bonus_type_keys?.length
      ? ` (${r.bonus_type_keys.join(", ")})`
      : "";
  return `${r.metric.replaceAll("_", " ")}${selector}: ${formatNumber(r.value)} ${r.direction}`;
}

export function Leaderboard({ league }: { league: League }) {
  const [phase, setPhase] = useState(league.phases[0]?.key || "overall");
  const [result, setResult] = useState<StandingsResponse>();
  const [error, setError] = useState("");

  useEffect(() => {
    setResult(undefined);
    setError("");
    api<StandingsResponse>(`/leagues/${league.id}/standings?phase=${encodeURIComponent(phase)}`)
      .then(setResult)
      .catch((e) => setError(errorMessage(e)));
  }, [league.id, phase]);

  const rows = result?.entries;

  return (
    <section className="panel stack">
      <div className="row between">
        <div>
          <p className="eyebrow">Leaderboard</p>
          <h2>{result?.phase.name || phase}</h2>
          {result && (
            <small className="muted">
              {result.phase.matching_matches === 0
                ? "No matching fixtures"
                : result.phase.is_final
                  ? "Final"
                  : `${result.phase.remaining_matches} remaining`}{" "}
              · {result.phase.finished_matches}/{result.phase.matching_matches} finished
            </small>
          )}
        </div>
        <label>
          Phase
          <select value={phase} onChange={(e) => setPhase(e.target.value)}>
            {uniquePhases(league).map((p) => (
              <option value={p.key} key={p.key}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? (
        <ErrorState error={error} />
      ) : !rows ? (
        <Loading label="Loading standings" />
      ) : !rows.length ? (
        <Empty title="No scored matches yet" />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Manager</th>
                <th>Total</th>
                <th>Upset</th>
                <th>Wins</th>
                <th>Payout</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const tied = i > 0 && rows[i - 1].rank === r.rank;
                return (
                  <tr key={r.member_id}>
                    <td>
                      <span className={`rank ${r.rank === 1 ? "first" : ""}`}>{r.rank}</span>
                    </td>
                    <td>
                      <strong>{r.display_name}</strong>
                      {tied && <small className="muted"> · tied</small>}
                      <small className="muted" style={{ display: "block" }}>
                        {r.metric_values.map(rungLabel).join(" → ")}
                      </small>
                    </td>
                    <td>{formatNumber(r.total_points)}</td>
                    <td>{formatNumber(r.upset_points)}</td>
                    <td>{r.win_count}</td>
                    <td>{Number(r.payout) > 0 ? `$${formatNumber(r.payout)}` : "—"}</td>
                    <td>
                      <Status
                        value={
                          result?.phase.matching_matches === 0
                            ? "no fixtures"
                            : result?.phase.is_final
                              ? "final"
                              : "active"
                        }
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="grid grid-3">
        {uniquePhases(league).map((p) => (
          <button
            key={p.key}
            type="button"
            className={phase === p.key ? "" : "secondary"}
            onClick={() => setPhase(p.key)}
          >
            {p.name}
            <small style={{ opacity: 0.8 }}>
              {p.finished_matches}/{p.matching_matches}
            </small>
          </button>
        ))}
      </div>
    </section>
  );
}
