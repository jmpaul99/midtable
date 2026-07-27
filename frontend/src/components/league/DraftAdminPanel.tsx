"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { League, PoolTeam, UUID } from "@/lib/types";
import { ErrorState } from "@/components/ui/State";
import { Stack } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/ToastProvider";
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
  const { toast } = useToast();
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
  /** Empty = all competitions for the preassign team list. */
  const [teamPool, setTeamPool] = useState("");
  const [poolTeams, setPoolTeams] = useState<Record<string, PoolTeam[]>>({});
  const [loadError, setLoadError] = useState("");
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [preassignConfirmOpen, setPreassignConfirmOpen] = useState(false);
  const pendingPreassignForm = useRef<HTMLFormElement | null>(null);

  const settingsEditable = league.status === "pre_draft";

  const loadPoolTeams = useCallback(() => {
    setLoadError("");
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
      .catch((e) => setLoadError(errorMessage(e)));
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
    if (!settingsEditable) return;
    const target = index + direction;
    if (target < 0 || target >= draftOrder.length) return;
    const next = [...draftOrder];
    [next[index], next[target]] = [next[target], next[index]];
    setDraftOrder(next);
  }

  async function saveOrder() {
    if (!settingsEditable) return;
    try {
      await api(`/leagues/${league.id}/draft-order`, json("PUT", { member_ids: draftOrder }));
      toast({ message: "Draft order saved." });
      onLeagueChange?.();
      loadPoolTeams();
    } catch (e) {
      toast({
        message: errorMessage(e),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
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
    try {
      await api(`/leagues/${league.id}/settings`, json("PATCH", patch));
      toast({
        message:
          patch.preassign_mode === "none"
            ? "Draft settings saved. Preassigned clubs were cleared."
            : "Draft settings saved.",
      });
      onLeagueChange?.();
      if (patch.preassign_mode === "none") {
        loadPoolTeams();
      }
    } catch (e) {
      setDraftStyle(prevStyle);
      setPreassignMode(prevMode);
      toast({
        message: errorMessage(e),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setSettingsBusy(false);
    }
  }

  function preassign(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    pendingPreassignForm.current = e.currentTarget;
    setPreassignConfirmOpen(true);
  }

  async function confirmPreassign() {
    const form = pendingPreassignForm.current;
    pendingPreassignForm.current = null;
    setPreassignConfirmOpen(false);
    if (!form) return;
    const f = new FormData(form);
    const teamId = String(f.get("team") || "");
    const memberId = String(f.get("member") || "");
    // Combined "all competitions" mode encodes pool in the option value as poolId:teamId.
    let poolId = String(f.get("pool") || "");
    let resolvedTeamId = teamId;
    if (teamId.includes(":")) {
      const [encodedPool, encodedTeam] = teamId.split(":");
      if (encodedPool && encodedTeam) {
        poolId = encodedPool;
        resolvedTeamId = encodedTeam;
      }
    }
    if (!poolId || !resolvedTeamId || !memberId) {
      toast({
        message: "Choose a manager and available team.",
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
      return;
    }
    try {
      await api(`/leagues/${league.id}/preassigns`, json("POST", {
        member_id: memberId,
        team_id: resolvedTeamId,
        pool_id: poolId,
      }));
      toast({ message: "Team preassigned." });
      onLeagueChange?.();
      loadPoolTeams();
    } catch (err) {
      toast({
        message: errorMessage(err),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    }
  }

  return (
    <Stack gap="md">
      {loadError && <ErrorState error={loadError} retry={loadPoolTeams} />}
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
      <ConfirmDialog
        open={preassignConfirmOpen}
        title="Preassign this team?"
        description="The selected team will be assigned to this manager before the draft."
        confirmLabel="Preassign"
        cancelLabel="Cancel"
        tone="warning"
        onCancel={() => {
          pendingPreassignForm.current = null;
          setPreassignConfirmOpen(false);
        }}
        onConfirm={() => void confirmPreassign()}
      />
    </Stack>
  );
}
