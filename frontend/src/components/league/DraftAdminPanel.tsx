"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { League, PoolTeam, UUID } from "@/lib/types";
import { ErrorState, StatusBanner } from "@/components/ui/State";
import { Stack } from "@/components/ui/Card";
import { DraftOrderSection } from "@/components/admin/DraftOrderSection";
import { RosterCorrectionsSection } from "@/components/admin/RosterCorrectionsSection";

type DraftStyle = "linear" | "snake";
type PreassignMode = "none" | "supported" | "optional";

function normalizeDraftStyle(value: string | undefined): DraftStyle {
  return value === "snake" ? "snake" : "linear";
}

function normalizePreassignMode(value: string | undefined): PreassignMode {
  if (value === "supported" || value === "optional") return value;
  return "none";
}

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
  const [draftStyle, setDraftStyle] = useState<DraftStyle>(() =>
    normalizeDraftStyle(league.draft_style),
  );
  const [preassignMode, setPreassignMode] = useState<PreassignMode>(() =>
    normalizePreassignMode(league.preassign_mode),
  );
  const [teamPool, setTeamPool] = useState(league.pools[0]?.id || "");
  const [poolTeams, setPoolTeams] = useState<Record<string, PoolTeam[]>>({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [settingsBusy, setSettingsBusy] = useState(false);

  const settingsEditable = league.status === "pre_draft";

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

  useEffect(() => {
    setDraftStyle(normalizeDraftStyle(league.draft_style));
    setPreassignMode(normalizePreassignMode(league.preassign_mode));
  }, [league.draft_style, league.preassign_mode]);

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

  async function saveDraftSetting(patch: {
    draft_style?: DraftStyle;
    preassign_mode?: PreassignMode;
  }) {
    if (!settingsEditable || settingsBusy) return;
    const prevStyle = draftStyle;
    const prevMode = preassignMode;
    if (patch.draft_style != null) setDraftStyle(patch.draft_style);
    if (patch.preassign_mode != null) setPreassignMode(patch.preassign_mode);
    setSettingsBusy(true);
    setError("");
    setMessage("");
    try {
      await api(`/leagues/${league.id}/settings`, json("PATCH", patch));
      setMessage(
        patch.preassign_mode === "none"
          ? "Draft settings saved. Preassigned clubs were cleared."
          : "Draft settings saved.",
      );
      onLeagueChange?.();
      if (patch.preassign_mode === "none") {
        loadPoolTeams();
      }
    } catch (e) {
      setDraftStyle(prevStyle);
      setPreassignMode(prevMode);
      setError(errorMessage(e));
    } finally {
      setSettingsBusy(false);
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
          draftStyle={draftStyle}
          preassignMode={preassignMode}
          settingsEditable={settingsEditable}
          settingsBusy={settingsBusy}
          teamPool={teamPool}
          poolTeams={poolTeams}
          onMove={moveMember}
          onTeamPool={setTeamPool}
          onSaveOrder={saveOrder}
          onDraftStyleChange={(value) => void saveDraftSetting({ draft_style: value })}
          onPreassignModeChange={(value) => void saveDraftSetting({ preassign_mode: value })}
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
