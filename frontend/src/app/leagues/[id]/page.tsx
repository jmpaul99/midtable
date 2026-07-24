"use client";

import { use } from "react";
import { Leaderboard } from "@/components/Leaderboard";
import { LeagueShell } from "@/components/LeagueShell";

export default function LeagueStandingsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <LeagueShell leagueId={id}>
      {(league) => (
        <div className="stack">
          <section className="grid grid-3">
            <div className="panel">
              <p className="eyebrow">Managers</p>
              <div className="metric">
                {league.members.length}/{league.max_members}
              </div>
            </div>
            <div className="panel">
              <p className="eyebrow">Pools</p>
              <div className="metric">{league.pools.length}</div>
            </div>
            <div className="panel">
              <p className="eyebrow">Draft format</p>
              <div className="metric" style={{ fontSize: "1.25rem" }}>
                {String(league.settings.format || "linear")}
              </div>
            </div>
          </section>
          <Leaderboard league={league} />
        </div>
      )}
    </LeagueShell>
  );
}
