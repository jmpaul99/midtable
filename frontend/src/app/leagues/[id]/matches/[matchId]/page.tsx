"use client";

import { use } from "react";
import { useLeague } from "@/components/LeagueShell";
import { SnapshotAudit } from "@/components/SnapshotAudit";
import { PageHeader, Stack } from "@/components/ui/Card";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";

export default function MatchSnapshotPage({
  params,
}: {
  params: Promise<{ id: string; matchId: string }>;
}) {
  const { matchId } = use(params);
  const league = useLeague();
  return (
    <Stack gap="md" className="animate-in">
      <PageHeader
        breadcrumbs={
          <Breadcrumbs
            items={[
              { label: "Matches", href: `/leagues/${league.id}/matches` },
              { label: "Snapshot" },
            ]}
          />
        }
        title="Match snapshot"
        description={`Snapshot audit for match ${matchId}`}
      />
      <SnapshotAudit leagueId={league.id} matchId={matchId} />
    </Stack>
  );
}
