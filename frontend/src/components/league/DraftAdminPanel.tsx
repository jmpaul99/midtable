"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { League, PoolTeam, RosterRow, UUID } from "@/lib/types";
import { ErrorState } from "@/components/ui/State";
import { Stack } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/ToastProvider";
import { DraftOrderSection, type PreassignMode } from "@/components/admin/DraftOrderSection";
import { RosterCorrectionsSection } from "@/components/admin/RosterCorrectionsSection";
import {
  fromDatetimeLocalValue,
  parsePickTimerSeconds,
  toDatetimeLocalValue,
} from "@/components/settings/DraftTimingFields";

type DraftStyle = "linear" | "snake";

function normalizeDraftStyle(value: string | undefined): DraftStyle {
  return value === "snake" ? "snake" : "linear";
}

function normalizePreassignMode(value: string | undefined): PreassignMode {
  if (value === "optional" || value === "required") return value;
  if (value === "supported") return "required";
  if (value === "none" || value === "off") return "off";
  return "off";
}

function normalizePreassignCount(value: number | undefined | null): number {
  if (value == null || !Number.isFinite(value) || value < 0) return 1;
  return Math.floor(value);
}

function initialScheduledLocal(league: League): string {
  return toDatetimeLocalValue(
    league.draft_scheduled_at ??
      (typeof league.settings?.draft_scheduled_at === "string"
        ? league.settings.draft_scheduled_at
        : null),
  );
}

function initialPickTimerSeconds(league: League): string {
  const existing =
    league.pick_timer_seconds ??
    (typeof league.settings?.pick_timer_seconds === "number"
      ? league.settings.pick_timer_seconds
      : null);
  return existing != null && existing > 0 ? String(existing) : "";
}

function currentPickTimerSeconds(league: League): number | null {
  const existing =
    league.pick_timer_seconds ??
    (typeof league.settings?.pick_timer_seconds === "number"
      ? league.settings.pick_timer_seconds
      : null);
  return existing != null && existing > 0 ? existing : null;
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
  const [preassignCount, setPreassignCount] = useState(() =>
    normalizePreassignCount(
      league.preassign_count ??
        (typeof league.settings?.preassign_count === "number"
          ? league.settings.preassign_count
          : null),
    ),
  );
  const [scheduledLocal, setScheduledLocal] = useState(() => initialScheduledLocal(league));
  const [pickTimerSeconds, setPickTimerSeconds] = useState(() =>
    initialPickTimerSeconds(league),
  );
  /** Empty = all competitions for the preassign team list. */
  const [teamPool, setTeamPool] = useState("");
  const [poolTeams, setPoolTeams] = useState<Record<string, PoolTeam[]>>({});
  const [loadError, setLoadError] = useState("");
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [preassignConfirmOpen, setPreassignConfirmOpen] = useState(false);
  const [preassignOffConfirmOpen, setPreassignOffConfirmOpen] = useState(false);
  const [preassignOffCount, setPreassignOffCount] = useState<number | null>(null);
  const pendingPreassignForm = useRef<HTMLFormElement | null>(null);

  const settingsEditable = league.status === "pre_draft";
  const scheduleEditable = league.status === "pre_draft";
  const timerEditable = league.status !== "complete";

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
    setPreassignCount(
      normalizePreassignCount(
        league.preassign_count ??
          (typeof league.settings?.preassign_count === "number"
            ? league.settings.preassign_count
            : null),
      ),
    );
  }, [
    league.draft_style,
    league.preassign_mode,
    league.preassign_count,
    league.settings?.preassign_count,
  ]);

  useEffect(() => {
    setScheduledLocal(initialScheduledLocal(league));
  }, [league.draft_scheduled_at, league.settings?.draft_scheduled_at]);

  useEffect(() => {
    setPickTimerSeconds(initialPickTimerSeconds(league));
  }, [league.pick_timer_seconds, league.settings?.pick_timer_seconds]);

  function moveMember(index: number, direction: -1 | 1) {
    if (!settingsEditable) return;
    const target = index + direction;
    if (target < 0 || target >= draftOrder.length) return;
    const next = [...draftOrder];
    [next[index], next[target]] = [next[target], next[index]];
    setDraftOrder(next);
  }

  async function requestPreassignModeChange(value: PreassignMode) {
    if (value !== "off") {
      const nextCount =
        value === "required" && preassignCount < 1 ? 1 : preassignCount;
      void saveDraftSetting({
        preassign_mode: value,
        preassign_count: nextCount,
      });
      return;
    }
    if (settingsBusy) return;

    // Count from the server roster — local poolTeams may still be loading, failed, or stale.
    setSettingsBusy(true);
    try {
      const rows = await api<RosterRow[]>(`/leagues/${league.id}/rosters`);
      const count = rows.filter((r) => r.acquired_via === "preassigned").length;
      if (count > 0) {
        setPreassignOffCount(count);
        setPreassignOffConfirmOpen(true);
        return;
      }
    } catch {
      // Can't verify count — require confirmation rather than clearing silently.
      setPreassignOffCount(null);
      setPreassignOffConfirmOpen(true);
      return;
    } finally {
      setSettingsBusy(false);
    }

    void saveDraftSetting({ preassign_mode: value });
  }

  async function saveDraftSetting(patch: {
    draft_style?: DraftStyle;
    preassign_mode?: PreassignMode;
    preassign_count?: number;
  }) {
    if (!settingsEditable || settingsBusy) return;
    if (
      (patch.preassign_mode ?? preassignMode) === "required" &&
      (patch.preassign_count ?? preassignCount) < 1
    ) {
      toast({
        message: "Required preassign mode needs at least 1 team per manager.",
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
      return;
    }
    const prevStyle = draftStyle;
    const prevMode = preassignMode;
    const prevCount = preassignCount;
    if (patch.draft_style != null) setDraftStyle(patch.draft_style);
    if (patch.preassign_mode != null) setPreassignMode(patch.preassign_mode);
    if (patch.preassign_count != null) setPreassignCount(patch.preassign_count);
    setSettingsBusy(true);
    try {
      await api(`/leagues/${league.id}/settings`, json("PATCH", patch));
      toast({
        message:
          patch.preassign_mode === "off"
            ? "Draft settings saved. Preassigned clubs were cleared."
            : "Draft settings saved.",
      });
      onLeagueChange?.();
      if (patch.preassign_mode === "off") {
        loadPoolTeams();
      }
    } catch (e) {
      setDraftStyle(prevStyle);
      setPreassignMode(prevMode);
      setPreassignCount(prevCount);
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

  async function saveDraftSettings() {
    if (settingsBusy) return;
    if (timerEditable && pickTimerSeconds.trim()) {
      const parsedTimer = Number(pickTimerSeconds);
      if (!Number.isInteger(parsedTimer) || parsedTimer < 1) {
        toast({
          message: "Seconds per pick must be a whole number of at least 1, or left blank.",
          tone: "error",
          durationMs: 6000,
          dismissible: true,
        });
        return;
      }
    }

    setSettingsBusy(true);
    let timingSaved = false;
    try {
      const nextTimer = parsePickTimerSeconds(pickTimerSeconds);
      const prevTimer = currentPickTimerSeconds(league);
      const timingPatch = {
        ...(scheduleEditable
          ? { draft_scheduled_at: fromDatetimeLocalValue(scheduledLocal) }
          : {}),
        // Only send the timer when it changed — PATCH always restarts an open pick clock.
        ...(timerEditable && nextTimer !== prevTimer
          ? { pick_timer_seconds: nextTimer }
          : {}),
      };
      if (Object.keys(timingPatch).length > 0) {
        await api(`/leagues/${league.id}/settings`, json("PATCH", timingPatch));
        timingSaved = true;
      }
      if (settingsEditable) {
        await api(`/leagues/${league.id}/draft-order`, json("PUT", { member_ids: draftOrder }));
      }
      toast({ message: "Draft settings saved." });
      onLeagueChange?.();
      if (settingsEditable) loadPoolTeams();
    } catch (e) {
      if (timingSaved) {
        toast({
          message: `Draft timing was saved, but draft order failed: ${errorMessage(e)}`,
          tone: "error",
          durationMs: 8000,
          dismissible: true,
        });
        onLeagueChange?.();
      } else {
        toast({
          message: errorMessage(e),
          tone: "error",
          durationMs: 6000,
          dismissible: true,
        });
      }
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
          preassignCount={preassignCount}
          settingsEditable={settingsEditable}
          settingsBusy={settingsBusy}
          teamPool={teamPool}
          poolTeams={poolTeams}
          scheduledLocal={scheduledLocal}
          pickTimerSeconds={pickTimerSeconds}
          scheduleEditable={scheduleEditable}
          timerEditable={timerEditable}
          onMove={moveMember}
          onTeamPool={setTeamPool}
          onDraftStyleChange={(value) => void saveDraftSetting({ draft_style: value })}
          onPreassignModeChange={requestPreassignModeChange}
          onPreassignCountChange={(value) =>
            void saveDraftSetting({ preassign_count: value })
          }
          onPreassign={preassign}
          onScheduledLocalChange={setScheduledLocal}
          onPickTimerSecondsChange={setPickTimerSeconds}
          onSave={() => void saveDraftSettings()}
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
        title="Assign this club before the draft?"
        description="The selected club will be given to this manager now and will not be available in the live draft."
        confirmLabel="Assign club"
        cancelLabel="Cancel"
        tone="warning"
        onCancel={() => {
          pendingPreassignForm.current = null;
          setPreassignConfirmOpen(false);
        }}
        onConfirm={() => void confirmPreassign()}
      />
      <ConfirmDialog
        open={preassignOffConfirmOpen}
        title="Turn off preassign?"
        description={
          preassignOffCount != null && preassignOffCount > 0
            ? `Switching to Off will clear ${preassignOffCount} preassigned club${preassignOffCount === 1 ? "" : "s"}. Managers will lose those clubs.`
            : "Switching to Off will clear any preassigned clubs. Managers will lose those clubs."
        }
        confirmLabel="Clear preassigns"
        cancelLabel="Cancel"
        tone="warning"
        onCancel={() => setPreassignOffConfirmOpen(false)}
        onConfirm={() => {
          setPreassignOffConfirmOpen(false);
          void saveDraftSetting({ preassign_mode: "off" });
        }}
      />
    </Stack>
  );
}
