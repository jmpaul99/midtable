"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { RequireAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import type { League } from "@/lib/types";
import { LeagueNav } from "./Nav";
import { ErrorState, Loading, Status } from "./State";

export function LeagueShell({
  leagueId,
  children,
  requireCommissioner = false,
}: {
  leagueId: string;
  children: (league: League) => ReactNode;
  requireCommissioner?: boolean;
}) {
  const [league, setLeague] = useState<League>();
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    api<League>(`/leagues/${leagueId}`)
      .then(setLeague)
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  useEffect(() => {
    load();
  }, [load]);

  const commissioner = league?.role === "owner" || league?.role === "commissioner";

  return (
    <RequireAuth>
      {!league && !error ? (
        <Loading label="Opening league" />
      ) : error && !league ? (
        <ErrorState error={error} retry={load} />
      ) : league ? (
        requireCommissioner && !commissioner ? (
          <ErrorState error="Commissioner access required." />
        ) : (
          <div className="stack">
            <header className="section-head">
              <div>
                <div className="row">
                  <p className="eyebrow" style={{ margin: 0 }}>
                    {league.season}
                  </p>
                  <Status value={league.status} />
                </div>
                <h1>{league.name}</h1>
                <p className="muted">
                  {league.members.length} of {league.max_members} managers · {league.visibility}
                </p>
              </div>
            </header>
            <LeagueNav leagueId={league.id} role={league.role} />
            {children(league)}
          </div>
        )
      ) : null}
    </RequireAuth>
  );
}
