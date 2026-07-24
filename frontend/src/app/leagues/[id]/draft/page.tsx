"use client";

import { use } from "react";
import { DraftBoard } from "@/components/DraftBoard";
import { LeagueShell } from "@/components/LeagueShell";

export default function LeagueDraftPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <LeagueShell leagueId={id}>
      {(league) => (
        <DraftBoard
          league={league}
          commissioner={league.role === "owner" || league.role === "commissioner"}
        />
      )}
    </LeagueShell>
  );
}
