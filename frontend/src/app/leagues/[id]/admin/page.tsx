"use client";

import { use } from "react";
import { AdminPanel } from "@/components/AdminPanel";
import { LeagueShell } from "@/components/LeagueShell";

export default function LeagueAdminPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <LeagueShell leagueId={id} requireCommissioner>
      {(league) => <AdminPanel league={league} />}
    </LeagueShell>
  );
}
