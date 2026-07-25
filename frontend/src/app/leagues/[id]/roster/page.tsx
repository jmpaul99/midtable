"use client";

import { useLeagueContext } from "@/components/LeagueShell";
import { RosterGrid } from "@/components/RosterGrid";

export default function LeagueRosterPage() {
  const { league, reload } = useLeagueContext();
  return (
    <RosterGrid
      leagueId={league.id}
      members={league.members}
      currentMemberId={league.current_member_id}
      onTeamNameSaved={reload}
      leagueStatus={league.status}
      rosterClubOrder={league.roster_club_order}
    />
  );
}
