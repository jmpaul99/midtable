"use client";

import { use } from "react";
import { useLeagueContext } from "@/components/LeagueShell";
import { ManagerPage } from "@/components/league/ManagerPage";

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
    />
  );
}
