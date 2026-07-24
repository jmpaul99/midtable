"use client";

import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { RosterRow, UUID } from "@/lib/types";
import { Empty, ErrorState, Loading } from "./State";

export function RosterGrid({ leagueId }: { leagueId: UUID }) {
  const [rows, setRows] = useState<RosterRow[]>();
  const [error, setError] = useState("");

  useEffect(() => {
    api<RosterRow[]>(`/leagues/${leagueId}/rosters`)
      .then(setRows)
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  const grouped = useMemo(
    () =>
      Object.entries(
        (rows || []).reduce<Record<string, RosterRow[]>>((acc, row) => {
          const key = `${row.display_name} · ${row.pool_name}`;
          (acc[key] ??= []).push(row);
          return acc;
        }, {}),
      ),
    [rows],
  );

  if (error) return <ErrorState error={error} />;
  if (!rows) return <Loading label="Loading rosters" />;
  if (!rows.length) return <Empty title="No roster slots found" />;

  return (
    <div className="grid grid-3">
      {grouped.map(([name, items]) => (
        <section className="panel" key={name}>
          <h3>{name}</h3>
          <div className="stack">
            {items.map((r) => (
              <div
                className="row panel inset"
                key={`${r.member_id}-${r.pool_id}-${r.slot_number}`}
              >
                <span className="rank">{r.slot_number}</span>
                <div>
                  <strong>{r.team_name || "Open slot"}</strong>
                  <div className="muted">
                    {r.acquired_via?.replaceAll("_", " ") || "Awaiting draft"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
