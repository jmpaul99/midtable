"use client";

import Link from "next/link";
import { use } from "react";
import { LeagueShell } from "@/components/LeagueShell";
import { SnapshotAudit } from "@/components/SnapshotAudit";

export default function MatchSnapshotPage({
  params,
}: {
  params: Promise<{ id: string; matchId: string }>;
}) {
  const { id, matchId } = use(params);
  return (
    <LeagueShell leagueId={id}>
      {() => (
        <div className="stack">
          <div className="row between">
            <p className="muted">Snapshot audit for match {matchId}</p>
            <Link className="button secondary" href={`/leagues/${id}/matches`}>
              Back to match log
            </Link>
          </div>
          <SnapshotAudit leagueId={id} matchId={matchId} />
        </div>
      )}
    </LeagueShell>
  );
}
