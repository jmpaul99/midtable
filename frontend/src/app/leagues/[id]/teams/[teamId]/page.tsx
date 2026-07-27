"use client";

import { use } from "react";
import { useLeague } from "@/components/LeagueShell";
import { TeamPage } from "@/components/league/TeamPage";
import { upsetNameByKey } from "@/components/settings/types";

export default function LeagueTeamPage({
  params,
}: {
  params: Promise<{ id: string; teamId: string }>;
}) {
  const { teamId } = use(params);
  const league = useLeague();
  return (
    <TeamPage
      leagueId={league.id}
      leagueName={league.name}
      teamId={teamId}
      eventTypeLabels={upsetNameByKey(league.upset_rules)}
    />
  );
}
