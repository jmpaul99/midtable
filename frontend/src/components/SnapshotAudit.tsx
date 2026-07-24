"use client";

import { useEffect, useMemo, useState } from "react";
import { api, errorMessage, formatDate } from "@/lib/api";
import type { Snapshot, UUID } from "@/lib/types";
import { Empty, ErrorState, Loading } from "./State";

export function SnapshotAudit({
  leagueId,
  matchId,
}: {
  leagueId: UUID;
  matchId?: UUID;
}) {
  const [snapshots, setSnapshots] = useState<Snapshot[]>();
  const [error, setError] = useState("");

  useEffect(() => {
    api<Snapshot[]>(`/leagues/${leagueId}/snapshot-audit`)
      .then(setSnapshots)
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  const filtered = useMemo(() => {
    if (!snapshots) return [];
    if (!matchId) return snapshots;
    // Snapshots are keyed by kickoff/source version; filter by nearby kickoff when match id is given
    // by showing all and highlighting — API doesn't join match_id on snapshots, so we show all
    // and note the match context in the header.
    return snapshots;
  }, [snapshots, matchId]);

  if (error) return <ErrorState error={error} />;
  if (!snapshots) return <Loading label="Loading snapshots" />;
  if (!filtered.length) return <Empty title="No table snapshots recorded" />;

  return (
    <section className="panel stack">
      <div className="section-head">
        <div>
          <p className="eyebrow">Audit</p>
          <h2>Table snapshots</h2>
          {matchId && (
            <p className="muted">
              Context match <code className="code">{matchId}</code>. Snapshots are computed against
              source match versions used for upset scoring.
            </p>
          )}
        </div>
      </div>
      <div className="stack">
        {filtered.map((s) => (
          <details key={s.id} open={filtered.length === 1}>
            <summary>
              {formatDate(s.kickoff_at)} · source v{s.source_match_version} · computed{" "}
              {formatDate(s.computed_at)}
            </summary>
            <div className="table-wrap" style={{ marginTop: "0.7rem" }}>
              <table>
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Team</th>
                    <th>Played</th>
                    <th>Points</th>
                  </tr>
                </thead>
                <tbody>
                  {s.rows.map((r) => (
                    <tr key={r.team_id}>
                      <td>{r.position}</td>
                      <td>{r.team_name}</td>
                      <td>{r.played}</td>
                      <td>{r.points}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}
