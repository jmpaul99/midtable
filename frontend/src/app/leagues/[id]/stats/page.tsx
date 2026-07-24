"use client";

import { useLeague } from "@/components/LeagueShell";
import { StatsDashboard } from "@/components/StatsDashboard";

export default function LeagueStatsPage() {
  const league = useLeague();
  return <StatsDashboard leagueId={league.id} />;
}
