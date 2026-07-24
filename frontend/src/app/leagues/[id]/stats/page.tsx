"use client";

import { use } from "react";
import { LeagueShell } from "@/components/LeagueShell";
import { StatsDashboard } from "@/components/StatsDashboard";

export default function LeagueStatsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <LeagueShell leagueId={id}>
      {() => <StatsDashboard leagueId={id} />}
    </LeagueShell>
  );
}
