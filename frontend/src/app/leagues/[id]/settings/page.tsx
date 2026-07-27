"use client";

import { useLeagueContext } from "@/components/LeagueShell";
import { LeagueSettingsView } from "@/components/league/LeagueSettingsView";

export default function LeagueSettingsPage() {
  const { league } = useLeagueContext();

  // TEMP: commissioner redirect disabled for testing the read-only view.
  // Restore: redirect commissioners to `/leagues/${league.id}/admin`.
  return <LeagueSettingsView league={league} />;
}
