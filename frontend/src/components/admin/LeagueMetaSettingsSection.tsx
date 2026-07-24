"use client";

import { FormEvent, useMemo, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { Invite, League, Manager, UUID } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { Status, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { BanIcon, SaveIcon, SendIcon, TrashIcon } from "@/components/ui/icons";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { Input, Label, Switch } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import {
  LeaguePoolsEditor,
  normalizePayouts,
  normalizePhases,
  PayoutsEditor,
  PhasesEditor,
  type LeaderboardPhase,
  type LeaguePoolEdit,
  type PayoutRow,
} from "@/components/settings";

type Tab = "basics" | "managers" | "pools" | "phases" | "payouts";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "basics", label: "Basics" },
  { id: "managers", label: "Managers" },
  { id: "pools", label: "Competitions" },
  { id: "phases", label: "Phases" },
  { id: "payouts", label: "Payouts" },
];

function poolsFromLeague(
  league: League,
  teamCounts: Record<string, number>,
): LeaguePoolEdit[] {
  return (league.pools || []).map((p, i) => ({
    id: p.id,
    key: p.key,
    label: p.label || p.name || p.key,
    sort_order: p.sort_order ?? i + 1,
    slot_count: p.slot_count ?? p.roster_size ?? 1,
    scores_match_results: p.scores_match_results ?? p.scoring_enabled ?? true,
    team_count: teamCounts[p.id] ?? 0,
  }));
}

export function LeagueMetaSettingsSection({
  league,
  teamCounts = {},
  bonusTypeOptions = [],
  invites,
  atOrOverCap = false,
  maxMembers = null,
  onInvite,
  onRevoke,
  onToggleCommissioner,
  onRemove,
  onSaved,
}: {
  league: League;
  teamCounts?: Record<string, number>;
  bonusTypeOptions?: Array<{ value: string; label: string }>;
  invites?: Invite[];
  atOrOverCap?: boolean;
  maxMembers?: number | null;
  onInvite?: (e: FormEvent<HTMLFormElement>) => void;
  onRevoke?: (id: UUID) => void;
  onToggleCommissioner?: (memberId: UUID, isCommissioner: boolean) => void;
  onRemove?: (memberId: UUID) => void;
  onSaved?: () => void;
}) {
  const [tab, setTab] = useState<Tab>("basics");
  const [name, setName] = useState(league.name || "");
  const [seasonLabel, setSeasonLabel] = useState(league.season_label || league.season || "");
  const [buyIn, setBuyIn] = useState(String(league.buy_in ?? 50));
  const [maxMembersValue, setMaxMembersValue] = useState(() => {
    const existing =
      league.max_members ??
      (typeof league.settings?.max_members === "number" ? league.settings.max_members : null);
    return String(existing ?? Math.max(league.members?.length || 0, 2));
  });
  const [phases, setPhases] = useState<LeaderboardPhase[]>(() =>
    normalizePhases(league.leaderboard_phases),
  );
  const [payouts, setPayouts] = useState<PayoutRow[]>(() => normalizePayouts(league.payouts));
  const [pools, setPools] = useState<LeaguePoolEdit[]>(() =>
    poolsFromLeague(league, teamCounts),
  );
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const memberCount = league.members?.length || 0;

  const managerCapacity = useMemo(() => {
    const parsed = Number(maxMembersValue);
    const max = Number.isFinite(parsed) ? parsed : null;
    return Math.max(memberCount, max || 0, 1);
  }, [maxMembersValue, memberCount]);

  const poolsWithCounts = useMemo(
    () =>
      pools.map((p) => ({
        ...p,
        team_count: teamCounts[p.id] ?? p.team_count ?? 0,
      })),
    [pools, teamCounts],
  );

  const capacityErrors = poolsWithCounts
    .filter((p) => {
      const teams = p.team_count ?? 0;
      if (teams <= 0) return false;
      return (Number(p.slot_count) || 0) * managerCapacity > teams;
    })
    .map((p) => {
      const needed = (Number(p.slot_count) || 0) * managerCapacity;
      return `${p.label}: ${p.slot_count} slots × ${managerCapacity} managers needs ${needed} clubs, but only ${p.team_count} are loaded.`;
    });

  async function save(e: FormEvent) {
    e.preventDefault();
    const trimmedName = name.trim();
    const trimmedSeason = seasonLabel.trim();
    const parsedMax = Number(maxMembersValue);
    if (!trimmedName || !trimmedSeason) {
      setError("League name and season label are required.");
      setTab("basics");
      return;
    }
    if (!Number.isInteger(parsedMax) || parsedMax < memberCount) {
      setError(
        memberCount > 0
          ? `Enter a whole number of managers at least ${memberCount} (current roster).`
          : "Enter a whole number of managers.",
      );
      setTab("basics");
      return;
    }
    if (capacityErrors.length) {
      setError(capacityErrors[0]);
      setTab("pools");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(
        `/leagues/${league.id}/settings`,
        json("PATCH", {
          name: trimmedName,
          season_label: trimmedSeason,
          buy_in: Number(buyIn),
          max_members: parsedMax,
          leaderboard_phases: phases,
          payouts,
          pools: pools.map((p) => ({
            id: p.id,
            label: p.label.trim(),
            sort_order: Number(p.sort_order),
            slot_count: Number(p.slot_count),
            scores_match_results: Boolean(p.scores_match_results),
          })),
        }),
      );
      setMessage("League settings saved.");
      onSaved?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <Stack>
        <Muted>Season identity, managers, competitions, phases, and payout structure.</Muted>
        {error && <StatusBanner tone="error">{error}</StatusBanner>}
        {message && <StatusBanner tone="success">{message}</StatusBanner>}

        <div
          className="flex gap-1 overflow-x-auto rounded-xl bg-surface-2 p-1"
          role="tablist"
          aria-label="League settings"
        >
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "min-h-11 shrink-0 rounded-lg px-3 py-2 text-xs font-bold transition sm:text-sm",
                tab === t.id ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "managers" ? (
          <div role="tabpanel">
            <ManagersInvitesPanel
              league={league}
              invites={invites}
              atOrOverCap={atOrOverCap}
              maxMembers={maxMembers}
              onInvite={onInvite}
              onRevoke={onRevoke}
              onToggleCommissioner={onToggleCommissioner}
              onRemove={onRemove}
            />
          </div>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={save}>
            <div role="tabpanel">
              {tab === "basics" && (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:items-start sm:gap-x-4 sm:gap-y-3">
                  <Label className="min-w-0">
                    League name
                    <Input
                      type="text"
                      name="name"
                      required
                      maxLength={120}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </Label>
                  <Label className="min-w-0">
                    Season label
                    <Input
                      type="text"
                      name="season_label"
                      required
                      maxLength={40}
                      placeholder="2026-27"
                      value={seasonLabel}
                      onChange={(e) => setSeasonLabel(e.target.value)}
                    />
                  </Label>
                  <Label className="min-w-0">
                    Buy-in
                    <Input
                      type="number"
                      step="0.01"
                      value={buyIn}
                      onChange={(e) => setBuyIn(e.target.value)}
                    />
                  </Label>
                  <div className="min-w-0">
                    <Label>
                      Managers
                    <Input
                      type="number"
                      name="max_members"
                      min={Math.max(1, memberCount)}
                      required
                      value={maxMembersValue}
                      onChange={(e) => setMaxMembersValue(e.target.value)}
                    />
                    </Label>
                    <Muted className="mt-1.5 font-normal text-[0.7rem] leading-snug">
                      League size — how many managers (teams) this league holds. Draft opens
                      when all have joined ({memberCount} of {Number(maxMembersValue) || "?"}{" "}
                      now).
                    </Muted>
                  </div>
                </div>
              )}
              {tab === "pools" && (
                <LeaguePoolsEditor
                  value={poolsWithCounts}
                  onChange={setPools}
                  managerCapacity={managerCapacity}
                />
              )}
              {tab === "phases" && (
                <PhasesEditor
                  value={phases}
                  onChange={setPhases}
                  bonusTypeOptions={bonusTypeOptions}
                />
              )}
              {tab === "payouts" && <PayoutsEditor value={payouts} onChange={setPayouts} />}
            </div>

            <div className="flex justify-start">
              <IconButton
                type="submit"
                label="Save league settings"
                variant="primary"
                busy={busy}
                disabled={capacityErrors.length > 0}
              >
                <SaveIcon />
              </IconButton>
            </div>
          </form>
        )}
      </Stack>
    </Card>
  );
}

function ManagersInvitesPanel({
  league,
  invites,
  atOrOverCap,
  maxMembers,
  onInvite,
  onRevoke,
  onToggleCommissioner,
  onRemove,
}: {
  league: League;
  invites?: Invite[];
  atOrOverCap: boolean;
  maxMembers: number | null;
  onInvite?: (e: FormEvent<HTMLFormElement>) => void;
  onRevoke?: (id: UUID) => void;
  onToggleCommissioner?: (memberId: UUID, isCommissioner: boolean) => void;
  onRemove?: (memberId: UUID) => void;
}) {
  const preDraft = league.status === "pre_draft";
  const commissionerCount = league.members.filter((m) => m.is_commissioner).length;
  const sorted = [...league.members].sort((a, b) => {
    const sa = a.draft_slot ?? Number.POSITIVE_INFINITY;
    const sb = b.draft_slot ?? Number.POSITIVE_INFINITY;
    if (sa !== sb) return sa - sb;
    return managerLabel(a).localeCompare(managerLabel(b));
  });

  function canDemote(m: Manager) {
    return !(m.is_commissioner && commissionerCount <= 1);
  }

  function canRemove(m: Manager) {
    if (!preDraft) return false;
    const isSelf = m.id === league.current_member_id;
    if (isSelf && m.is_commissioner && commissionerCount <= 1) return false;
    return true;
  }

  return (
    <Stack>
      {!preDraft && (
        <Muted className="text-xs">
          Managers can only be removed before the draft opens.
        </Muted>
      )}
      <Stack gap="sm">
        {sorted.map((m) => {
          const isSelf = m.id === league.current_member_id;
          const demoteOk = canDemote(m);
          const removeOk = canRemove(m);
          return (
            <div
              className="flex flex-col gap-3 rounded-xl border border-line bg-surface-2/50 p-3 sm:flex-row sm:items-center sm:justify-between"
              key={m.id}
            >
              <div className="min-w-0">
                <strong className="break-words">{managerLabel(m)}</strong>
                <Muted className="break-all">
                  {m.email || "No email"}
                  {m.draft_slot != null ? ` · Slot ${m.draft_slot}` : ""}
                  {isSelf ? " · You" : ""}
                </Muted>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2">
                  <Switch
                    size="sm"
                    checked={m.is_commissioner}
                    disabled={m.is_commissioner && !demoteOk}
                    onChange={(e) => {
                      const next = e.target.checked;
                      if (
                        !next &&
                        !confirm(`Remove commissioner access from ${managerLabel(m)}?`)
                      ) {
                        return;
                      }
                      onToggleCommissioner?.(m.id, next);
                    }}
                  />
                  <span className="text-xs font-semibold text-muted">Commissioner</span>
                </label>
                {preDraft && (
                  <IconButton
                    type="button"
                    variant="danger"
                    size="icon-sm"
                    label={
                      removeOk
                        ? "Remove manager"
                        : "Cannot remove the last commissioner"
                    }
                    disabled={!removeOk}
                    onClick={() => {
                      if (
                        confirm(
                          `Remove ${managerLabel(m)} from this league? Their preassigned clubs will be cleared.`,
                        )
                      ) {
                        onRemove?.(m.id);
                      }
                    }}
                  >
                    <TrashIcon className="size-4" />
                  </IconButton>
                )}
              </div>
            </div>
          );
        })}
      </Stack>

      {maxMembers != null && (
        <StatusBanner tone={atOrOverCap ? "success" : "info"}>
          {league.members.length} of {maxMembers} managers joined
          {atOrOverCap
            ? " — roster is full."
            : " — draft opens when the roster is full."}
        </StatusBanner>
      )}
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          onInvite?.(e);
        }}
      >
        <Label>
          Invite by email
          <div className="flex items-center gap-2">
            <Input type="email" name="email" required className="min-w-0 flex-1" />
            <IconButton type="submit" label="Send invite" variant="primary">
              <SendIcon />
            </IconButton>
          </div>
        </Label>
        <label className="flex w-fit max-w-full items-start gap-2">
          <Switch name="commissioner" size="sm" className="mt-0.5" />
          <span className="min-w-0">
            <span className="block text-xs font-semibold text-muted">Commissioner access</span>
            <Muted className="text-[0.7rem] leading-snug">
              Can manage league settings and invites
            </Muted>
          </span>
        </label>
      </form>
      {invites && invites.length > 0 && (
        <Stack gap="sm">
          {invites.map((i) => (
            <div
              className="flex flex-col gap-3 rounded-xl border border-line bg-surface-2/50 p-3 sm:flex-row sm:items-center sm:justify-between"
              key={i.id}
            >
              <div className="min-w-0">
                <strong className="break-all">{i.email}</strong>
                <Muted>
                  {i.is_commissioner
                    ? "Commissioner"
                    : i.role === "member" || !i.role
                      ? "Manager"
                      : i.role.replaceAll("_", " ")}
                </Muted>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Status value={i.status} />
                {i.status === "pending" && (
                  <IconButton
                    type="button"
                    variant="danger"
                    size="icon-sm"
                    label="Revoke invite"
                    onClick={() => {
                      if (confirm("Revoke this invite?")) onRevoke?.(i.id);
                    }}
                  >
                    <BanIcon className="size-4" />
                  </IconButton>
                )}
              </div>
            </div>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
