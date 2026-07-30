"use client";

import { use } from "react";
import { useLeague } from "@/components/LeagueShell";
import { MatchDetail } from "@/components/league/MatchDetail";
import { upsetNameByKey } from "@/components/settings/types";
import { PageHeader, Stack } from "@/components/ui/Card";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";

export default function MatchDetailPage({
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
              { label: "Match" },
            ]}
          />
        }
        title="Match"
        description="Result summary and scoring events"
      />
      <MatchDetail
        leagueId={league.id}
        matchId={matchId}
        eventTypeLabels={upsetNameByKey(league.upset_rules)}
      />
    </Stack>
  );
}
