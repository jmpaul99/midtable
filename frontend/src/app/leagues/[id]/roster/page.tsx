"use client";

import { use } from "react";
import { LeagueShell } from "@/components/LeagueShell";
import { RosterGrid } from "@/components/RosterGrid";

export default function LeagueRosterPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <LeagueShell leagueId={id}>
      {() => <RosterGrid leagueId={id} />}
    </LeagueShell>
  );
}
