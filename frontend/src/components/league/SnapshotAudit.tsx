"use client";

import { useEffect, useMemo, useState } from "react";
import { api, errorMessage, formatDate } from "@/lib/api";
import type { Json, Snapshot, UUID } from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import { Card, Eyebrow, Muted, Stack } from "@/components/ui/Card";
import { TeamLink } from "./TeamLink";

type MatchEventsPayload = {
  match_id: string;
  home_team_id: string;
  away_team_id: string;
  home_goals: number | null;
  away_goals: number | null;
  events: Array<{
    id: string;
    team_id: string | null;
    event_type: string;
    points: number;
    metadata?: Record<string, Json> | null;
  }>;
};

export function SnapshotAudit({
  leagueId,
  matchId,
}: {
  leagueId: UUID;
  matchId?: UUID;
}) {
  const [snapshots, setSnapshots] = useState<Snapshot[]>();
  const [matchEvents, setMatchEvents] = useState<MatchEventsPayload>();
  const [error, setError] = useState("");

  useEffect(() => {
    api<Snapshot[]>(`/leagues/${leagueId}/snapshot-audit`)
      .then(setSnapshots)
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  useEffect(() => {
    if (!matchId) {
      setMatchEvents(undefined);
      return;
    }
    api<MatchEventsPayload>(`/leagues/${leagueId}/matches/${matchId}/events`)
      .then(setMatchEvents)
      .catch(() => setMatchEvents(undefined));
  }, [leagueId, matchId]);

  const filtered = useMemo(() => {
    if (!snapshots) return [];
    return snapshots;
  }, [snapshots]);

  const upsetRows = (matchEvents?.events || []).filter((e) =>
    String(e.event_type).includes("upset"),
  );

  if (error) return <ErrorState error={error} />;
  if (!snapshots) return <Loading label="Loading snapshots" />;
  if (!filtered.length && !upsetRows.length) return <Empty title="No table snapshots recorded" />;

  return (
    <Card className="animate-in">
      <Stack>
        <div>
          <Eyebrow>Audit</Eyebrow>
          <h2>Table snapshots</h2>
          {matchId && (
            <Muted className="mt-1">
              Context match <code className="break-all rounded bg-surface-2 px-1.5 py-0.5 text-xs">{matchId}</code>
              {matchEvents
                ? ` · ${matchEvents.home_goals ?? "-"}–${matchEvents.away_goals ?? "-"}`
                : null}
              .
            </Muted>
          )}
        </div>

        {upsetRows.length > 0 && (
          <div className="rounded-xl border border-line bg-surface-2/50 p-3.5">
            <h3 className="mb-2 text-base font-extrabold">Upset call</h3>
            <Stack gap="sm">
              {upsetRows.map((e) => {
                const meta = e.metadata || {};
                return (
                  <div key={e.id}>
                    <strong>
                      {e.event_type.replaceAll("_", " ")}
                    </strong>{" "}
                    · {e.points} pts
                    <Muted className="mt-1 text-xs">
                      Underdog rank {String(meta.underdog_rank ?? meta.home_rank ?? "—")} · Opponent
                      rank {String(meta.opponent_rank ?? meta.away_rank ?? "—")} · Gap{" "}
                      {String(meta.gap ?? "—")}
                      {meta.rank_source ? ` · ${String(meta.rank_source)}` : ""}
                    </Muted>
                  </div>
                );
              })}
            </Stack>
          </div>
        )}

        <Stack gap="sm">
          {filtered.map((s) => (
            <details
              key={s.id}
              open={filtered.length === 1 || Boolean(matchId)}
              className="rounded-xl border border-line bg-surface-2/40 open:bg-surface"
            >
              <summary className="cursor-pointer list-none px-3.5 py-3 font-bold [&::-webkit-details-marker]:hidden">
                {formatDate(s.kickoff_at)} · {s.stale ? "stale" : "fresh"} · computed{" "}
                {formatDate(s.computed_at)}
              </summary>
              <ul className="flex flex-col gap-1.5 border-t border-line p-3">
                {s.rows.map((r) => (
                  <li
                    key={r.team_id}
                    className="flex items-center justify-between gap-3 rounded-lg bg-surface px-3 py-2.5 text-sm"
                  >
                    <span className="min-w-0 flex-1 truncate">
                      <span className="mr-2 font-extrabold tabular-nums text-muted">{r.position}</span>
                      {r.team_id ? (
                        <TeamLink leagueId={leagueId} teamId={r.team_id}>
                          {r.team_name || "Team"}
                        </TeamLink>
                      ) : (
                        r.team_name
                      )}
                    </span>
                    <span className="shrink-0 tabular-nums text-muted">
                      P{r.played} · {r.points} pts
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </Stack>
      </Stack>
    </Card>
  );
}
