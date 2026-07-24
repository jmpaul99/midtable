"use client";

import { AdminPanel } from "@/components/AdminPanel";
import { useLeagueContext } from "@/components/LeagueShell";
import { ErrorState } from "@/components/State";

export default function LeagueAdminPage() {
  const { league, isCommissioner, reload } = useLeagueContext();
  if (!isCommissioner) {
    return <ErrorState error="Commissioner access required." />;
  }
  return <AdminPanel league={league} onLeagueChange={reload} />;
}
