"use client";

import { use } from "react";
import { useLeagueContext } from "@/components/LeagueShell";
import { ManagerPage } from "@/components/league/ManagerPage";
import { upsetNameByKey } from "@/components/settings/types";

export default function LeagueManagerPage({
  params,
}: {
  params: Promise<{ id: string; managerId: string }>;
}) {
  const { managerId } = use(params);
  const { league, reload } = useLeagueContext();
  return (
    <ManagerPage
      leagueId={league.id}
      managerId={managerId}
      currentManagerId={league.current_member_id}
      onTeamNameSaved={reload}
      leagueStatus={league.status}
      rosterClubOrder={league.roster_club_order}
      eventTypeLabels={upsetNameByKey(league.upset_rules)}
    />
  );
}
