"use client";

import { useLeague } from "@/components/LeagueShell";
import { MatchLog } from "@/components/MatchLog";

export default function LeagueMatchesPage() {
  const league = useLeague();
  return <MatchLog leagueId={league.id} />;
}
