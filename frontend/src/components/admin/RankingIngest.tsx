"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { UUID } from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import { Card, Muted, Stack } from "@/components/ui/Card";

interface RankingStatusRow {
  id: UUID;
  key: string;
  label: string;
  source: string;
  as_of: string | null;
  locked: boolean;
  entry_count: number;
  unmatched_count: number;
  is_selected: boolean;
}

export function RankingIngest({ leagueId }: { leagueId: UUID }) {
  const { isAdmin } = useAuth();
  const [lists, setLists] = useState<RankingStatusRow[]>();
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<RankingStatusRow[]>(`/leagues/${leagueId}/ranking-lists`)
      .then(setLists)
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!lists) return <Loading label="Loading ranking lists…" />;

  return (
    <Card>
      <Stack>
        <div>
          <h2>Ranking lists</h2>
          <Muted className="mt-1">
            Fixed ranks used for upset scoring. System lists refresh via sync; platform admins can
            rematch unmatched countries globally.
          </Muted>
        </div>
        {error && <ErrorState error={error} />}

        {lists.length === 0 ? (
          <Empty title="No ranking list selected" />
        ) : (
          <ul className="flex flex-col gap-2">
            {lists.map((l) => (
              <li
                key={l.id}
                className="rounded-xl border border-line bg-surface-2/50 px-3 py-2.5 text-sm"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <strong>{l.label}</strong>
                  <Muted className="text-xs">
                    {l.locked ? "Locked" : "Unlocked"}
                    {l.is_selected ? " · selected" : ""}
                  </Muted>
                </div>
                <Muted className="mt-1 text-xs">
                  {l.as_of ? `As of ${l.as_of}` : "No as-of date"}
                  {" · "}
                  {l.entry_count} ranked
                  {" · "}
                  {l.unmatched_count} unmatched
                </Muted>
              </li>
            ))}
          </ul>
        )}

        {isAdmin && (
          <Muted className="text-sm">
            Rematch unmatched countries on the{" "}
            <Link href="/admin/rankings" className="font-bold text-brand hover:underline">
              ranking rematch
            </Link>{" "}
            page.
          </Muted>
        )}
      </Stack>
    </Card>
  );
}
