"use client";

import { useLeague } from "@/components/LeagueShell";
import { StatsDashboard } from "@/components/StatsDashboard";
import { upsetNameByKey } from "@/components/settings/types";

export default function LeagueStatsPage() {
  const league = useLeague();
  return (
    <StatsDashboard
      leagueId={league.id}
      league={league}
      eventTypeLabels={upsetNameByKey(league.upset_rules)}
    />
  );
}
