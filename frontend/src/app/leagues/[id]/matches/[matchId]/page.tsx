"use client";

import Link from "next/link";
import { use } from "react";
import { useLeague } from "@/components/LeagueShell";
import { SnapshotAudit } from "@/components/SnapshotAudit";
import { Muted, Stack } from "@/components/ui/Card";

export default function MatchSnapshotPage({
  params,
}: {
  params: Promise<{ id: string; matchId: string }>;
}) {
  const { matchId } = use(params);
  const league = useLeague();
  return (
    <Stack gap="md" className="animate-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Muted className="min-w-0 break-all">Snapshot audit for match {matchId}</Muted>
        <Link
          href={`/leagues/${league.id}/matches`}
          className="inline-flex min-h-11 w-full shrink-0 items-center justify-center rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-bold hover:bg-surface-2 sm:w-auto"
        >
          Back to match log
        </Link>
      </div>
      <SnapshotAudit leagueId={league.id} matchId={matchId} />
    </Stack>
  );
}
