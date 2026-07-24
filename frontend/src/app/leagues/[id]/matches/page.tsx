"use client";

import { use } from "react";
import { LeagueShell } from "@/components/LeagueShell";
import { MatchLog } from "@/components/MatchLog";

export default function LeagueMatchesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <LeagueShell leagueId={id}>
      {() => <MatchLog leagueId={id} />}
    </LeagueShell>
  );
}
