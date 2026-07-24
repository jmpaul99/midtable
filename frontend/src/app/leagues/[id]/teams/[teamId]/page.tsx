"use client";

import { use } from "react";
import { useLeague } from "@/components/LeagueShell";
import { TeamPage } from "@/components/league/TeamPage";

export default function LeagueTeamPage({
  params,
}: {
  params: Promise<{ id: string; teamId: string }>;
}) {
  const { teamId } = use(params);
  const league = useLeague();
  return <TeamPage leagueId={league.id} teamId={teamId} />;
}
