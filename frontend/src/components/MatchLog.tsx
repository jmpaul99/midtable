"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, errorMessage, formatDate, formatNumber } from "@/lib/api";
import type { MatchEvent, UUID } from "@/lib/types";
import { Empty, ErrorState, Loading } from "./State";

export function MatchLog({ leagueId }: { leagueId: UUID }) {
  const [events, setEvents] = useState<MatchEvent[]>();
  const [error, setError] = useState("");

  useEffect(() => {
    api<MatchEvent[]>(`/leagues/${leagueId}/match-log`)
      .then(setEvents)
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  const matches = useMemo(() => {
    if (!events) return [];
    const map = new Map<
      string,
      { match_id: string; kickoff_at: string; matchday: number; events: MatchEvent[] }
    >();
    for (const event of events) {
      const existing = map.get(event.match_id);
      if (existing) existing.events.push(event);
      else {
        map.set(event.match_id, {
          match_id: event.match_id,
          kickoff_at: event.kickoff_at,
          matchday: event.matchday,
          events: [event],
        });
      }
    }
    return Array.from(map.values());
  }, [events]);

  if (error) return <ErrorState error={error} />;
  if (!events) return <Loading label="Loading match log" />;
  if (!events.length) return <Empty title="No scoring events yet" />;

  return (
    <section className="panel stack">
      <div className="section-head">
        <div>
          <p className="eyebrow">Scoring</p>
          <h2>Match log</h2>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Kickoff</th>
              <th>MW</th>
              <th>Team</th>
              <th>Owner</th>
              <th>Phase / event</th>
              <th>Points</th>
              <th>Audit</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <td>{formatDate(e.kickoff_at)}</td>
                <td>{e.matchday}</td>
                <td>{e.team_name}</td>
                <td>{e.display_name || "—"}</td>
                <td>
                  {e.phase} · {e.event_type}
                </td>
                <td>{formatNumber(e.points)}</td>
                <td>
                  <Link href={`/leagues/${leagueId}/matches/${e.match_id}`}>Snapshot</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        {matches.length} matches with scoring events. Open a snapshot audit from any row.
      </p>
    </section>
  );
}
