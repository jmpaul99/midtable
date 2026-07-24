"use client";

import { DraftBoard } from "@/components/DraftBoard";
import { useLeagueContext } from "@/components/LeagueShell";

export default function LeagueDraftPage() {
  const { league, isCommissioner, reload } = useLeagueContext();
  return (
    <DraftBoard league={league} commissioner={isCommissioner} onLeagueChange={reload} />
  );
}
