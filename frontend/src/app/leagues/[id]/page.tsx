"use client";

import { Leaderboard } from "@/components/Leaderboard";
import { useLeague } from "@/components/LeagueShell";

export default function LeagueStandingsPage() {
  const league = useLeague();
  return <Leaderboard league={league} />;
}
