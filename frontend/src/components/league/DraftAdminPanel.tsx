"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { League, PoolTeam, UUID } from "@/lib/types";
import { ErrorState, StatusBanner } from "@/components/ui/State";
import { Stack } from "@/components/ui/Card";
import { DraftOrderSection } from "@/components/admin/DraftOrderSection";
import { RosterCorrectionsSection } from "@/components/admin/RosterCorrectionsSection";

export function DraftAdminPanel({
  league,
  onLeagueChange,
}: {
  league: League;
  onLeagueChange?: () => void;
}) {
  const [draftOrder, setDraftOrder] = useState<UUID[]>(() =>
    [...league.members]
      .sort((a, b) => (a.draft_slot ?? 999) - (b.draft_slot ?? 999))
      .map((m) => m.id),
  );
  const [teamPool, setTeamPool] = useState(league.pools[0]?.id || "");
  const [poolTeams, setPoolTeams] = useState<Record<string, PoolTeam[]>>({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const loadPoolTeams = useCallback(() => {
    setError("");
    Promise.all(
      league.pools.map(async (p) => {
        try {
          const teams = await api<PoolTeam[]>(`/leagues/${league.id}/pools/${p.id}/teams`);
          return [p.id, teams] as const;
        } catch {
          return [p.id, [] as PoolTeam[]] as const;
        }
      }),
    )
      .then((entries) => setPoolTeams(Object.fromEntries(entries)))
      .catch((e) => setError(errorMessage(e)));
  }, [league.id, league.pools]);

  useEffect(() => {
    loadPoolTeams();
  }, [loadPoolTeams]);

  useEffect(() => {
    setDraftOrder(
      [...league.members]
        .sort((a, b) => (a.draft_slot ?? 999) - (b.draft_slot ?? 999))
        .map((m) => m.id),
    );
  }, [league.members]);

  function moveMember(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= draftOrder.length) return;
    const next = [...draftOrder];
    [next[index], next[target]] = [next[target], next[index]];
    setDraftOrder(next);
  }

  async function saveOrder() {
    setError("");
    setMessage("");
    try {
      await api(`/leagues/${league.id}/draft-order`, json("PUT", { member_ids: draftOrder }));
      setMessage("Draft order saved.");
      onLeagueChange?.();
      loadPoolTeams();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function preassign(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!confirm("Preassign this team?")) return;
    const f = new FormData(e.currentTarget);
    setError("");
    setMessage("");
    try {
      await api(`/leagues/${league.id}/preassigns`, json("POST", {
        member_id: f.get("member"),
        team_id: f.get("team"),
        pool_id: f.get("pool"),
      }));
      setMessage("Team preassigned.");
      onLeagueChange?.();
      loadPoolTeams();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Stack gap="md">
      {error && <ErrorState error={error} retry={loadPoolTeams} />}
      {message && <StatusBanner>{message}</StatusBanner>}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DraftOrderSection
          league={league}
          draftOrder={draftOrder}
          teamPool={teamPool}
          poolTeams={poolTeams}
          onMove={moveMember}
          onTeamPool={setTeamPool}
          onSaveOrder={saveOrder}
          onPreassign={preassign}
        />
        <RosterCorrectionsSection
          league={league}
          onChanged={() => {
            onLeagueChange?.();
            loadPoolTeams();
          }}
        />
      </div>
    </Stack>
  );
}
