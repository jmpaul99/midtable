"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Invite, JoinLink, League, Manager, UUID } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { Status, StatusBanner } from "@/components/ui/State";
import { useToast } from "@/components/ui/ToastProvider";
import { IconButton } from "@/components/ui/IconButton";
import {
  BanIcon,
  CopyIcon,
  RefreshIcon,
  SaveIcon,
  SendIcon,
  TrashIcon,
} from "@/components/ui/icons";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { Input, Label, Switch } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import { defaultFootballSeasonYear } from "@/lib/availableCompetitions";
import {
  normalizeRosterClubOrder,
  type RosterClubOrder,
} from "@/lib/rosterClubOrder";
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
    isNew: false,
    key: p.key,
    label: p.label || p.key,
    sort_order: p.sort_order ?? i + 1,
    slot_count: p.slot_count ?? 1,
    scores_match_results: p.scores_match_results ?? true,
    competition_code: p.competition_code || "",
    season_year: p.season_year ?? defaultFootballSeasonYear(),
    provider: p.provider || "football-data.org",
    team_count: teamCounts[p.id] ?? 0,
  }));
}

/**
 * True when pools were added/removed or competition code / season year changed.
 * Slot count, sort order, scoring flag, and roster club order do not need a reload.
 */
function competitionLoadSettingsChanged(
  league: League,
  pools: LeaguePoolEdit[],
  removePoolIds: string[],
): boolean {
  if (removePoolIds.length > 0) return true;
  if (pools.some((p) => p.isNew)) return true;
  const originalById = new Map((league.pools || []).map((p) => [p.id, p]));
  for (const p of pools) {
    if (p.isNew) continue;
    const orig = originalById.get(p.id);
    if (!orig) return true;
    if ((orig.competition_code || "").toUpperCase() !== (p.competition_code || "").toUpperCase()) {
      return true;
    }
    const origYear = Number(orig.season_year ?? defaultFootballSeasonYear());
    const nextYear = Number(p.season_year ?? defaultFootballSeasonYear());
    if (origYear !== nextYear) return true;
  }
  return false;
}

export function LeagueMetaSettingsSection({
  league,
  teamCounts = {},
  bonusTypeOptions = [],
  invites,
  joinLink,
  joinLinkBusy = false,
  atOrOverCap = false,
  maxMembers = null,
  onInvite,
  onResendInvite,
  onRevoke,
  onJoinLinkUpdate,
  onToggleCommissioner,
  onRemove,
  onSaved,
  onReloadTeams,
}: {
  league: League;
  teamCounts?: Record<string, number>;
  bonusTypeOptions?: Array<{ value: string; label: string }>;
  invites?: Invite[];
  joinLink?: JoinLink;
  joinLinkBusy?: boolean;
  atOrOverCap?: boolean;
  maxMembers?: number | null;
  onInvite?: (e: FormEvent<HTMLFormElement>) => void;
  onResendInvite?: (id: UUID) => void;
  onRevoke?: (id: UUID) => void;
  onJoinLinkUpdate?: (body: { enabled?: boolean; rotate?: boolean }) => void | Promise<unknown>;
  onToggleCommissioner?: (memberId: UUID, isCommissioner: boolean) => void;
  onRemove?: (memberId: UUID) => void;
  onSaved?: () => void;
  /** Load/reload clubs from the provider when competition settings change. */
  onReloadTeams?: (
    params: Array<{ key: string; competition_code: string; season_year: number }>,
  ) => Promise<void>;
}) {
  const [tab, setTab] = useState<Tab>("basics");
  const [name, setName] = useState(league.name || "");
  const [seasonLabel, setSeasonLabel] = useState(league.season_label || "");
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
  const [rosterClubOrder, setRosterClubOrder] = useState<RosterClubOrder>(() =>
    normalizeRosterClubOrder(league.roster_club_order),
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { toast } = useToast();

  const serverPoolIds = (league.pools || []).map((p) => p.id).join(",");
  useEffect(() => {
    setPools(poolsFromLeague(league, teamCounts));
    // Refresh editor rows when competitions are created/removed on the server.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- teamCounts applied via poolsWithCounts
  }, [serverPoolIds]);

  useEffect(() => {
    setRosterClubOrder(normalizeRosterClubOrder(league.roster_club_order));
  }, [league.roster_club_order]);

  const memberCount = league.members?.length || 0;
  const preDraft = league.status === "pre_draft";

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
    if (preDraft && (!Number.isInteger(parsedMax) || parsedMax < memberCount)) {
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
    const incomplete = pools.find((p) => !p.competition_code || !p.key || !p.label.trim());
    if (incomplete) {
      setError("Each competition needs a selection from the available list.");
      setTab("pools");
      return;
    }
    const originalIds = new Set((league.pools || []).map((p) => p.id));
    const keptIds = new Set(pools.filter((p) => !p.isNew).map((p) => p.id));
    const remove_pool_ids = [...originalIds].filter((id) => !keptIds.has(id));
    const shouldReloadTeams =
      Boolean(onReloadTeams) &&
      pools.length > 0 &&
      competitionLoadSettingsChanged(league, pools, remove_pool_ids);
    setBusy(true);
    setError("");
    try {
      await api(
        `/leagues/${league.id}/settings`,
        json("PATCH", {
          name: trimmedName,
          season_label: trimmedSeason,
          buy_in: Number(buyIn),
          ...(preDraft ? { max_members: parsedMax } : {}),
          roster_club_order: rosterClubOrder,
          leaderboard_phases: phases,
          payouts,
          remove_pool_ids: remove_pool_ids.length ? remove_pool_ids : undefined,
          pools: pools.map((p) =>
            p.isNew
              ? {
                  key: p.key,
                  label: p.label.trim(),
                  sort_order: Number(p.sort_order),
                  slot_count: Number(p.slot_count),
                  scores_match_results: Boolean(p.scores_match_results),
                  competition_code: p.competition_code,
                  season_year: Number(p.season_year),
                  provider: p.provider || "football-data.org",
                }
              : {
                  id: p.id,
                  label: p.label.trim(),
                  sort_order: Number(p.sort_order),
                  slot_count: Number(p.slot_count),
                  scores_match_results: Boolean(p.scores_match_results),
                  competition_code: p.competition_code || undefined,
                  season_year: Number(p.season_year) || undefined,
                  provider: p.provider || undefined,
                },
          ),
        }),
      );
      if (shouldReloadTeams && onReloadTeams) {
        try {
          await onReloadTeams(
            pools.map((p) => ({
              key: p.key,
              competition_code: p.competition_code,
              season_year: Number(p.season_year),
            })),
          );
          toast({ message: "League settings saved and clubs reloaded." });
        } catch (reloadErr) {
          toast({ message: "League settings saved." });
          toast({
            message: `Settings saved, but reloading clubs failed: ${errorMessage(reloadErr)}`,
            tone: "error",
            durationMs: 6000,
            dismissible: true,
          });
        }
      } else {
        toast({ message: "League settings saved." });
      }
      onSaved?.();
    } catch (err) {
      toast({
        message: errorMessage(err),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <Stack>
        <Muted>Season identity, managers, competitions, phases, and payout structure.</Muted>
        {error && <StatusBanner tone="error">{error}</StatusBanner>}

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
              joinLink={joinLink}
              joinLinkBusy={joinLinkBusy}
              atOrOverCap={atOrOverCap}
              maxMembers={maxMembers}
              onInvite={onInvite}
              onResendInvite={onResendInvite}
              onRevoke={onRevoke}
              onJoinLinkUpdate={onJoinLinkUpdate}
              onToggleCommissioner={onToggleCommissioner}
              onRemove={onRemove}
            />
          </div>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={save}>
            <div role="tabpanel">
              {tab === "basics" && (
                <div className="flex flex-col gap-3">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:items-start sm:gap-x-4">
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
                      Managers
                      <Input
                        type="number"
                        name="max_members"
                        min={Math.max(1, memberCount)}
                        required
                        disabled={!preDraft}
                        value={maxMembersValue}
                        onChange={(e) => setMaxMembersValue(e.target.value)}
                      />
                    </Label>
                  </div>
                  <Muted className="font-normal text-[0.7rem] leading-snug">
                    {preDraft
                      ? `League size — how many managers (teams) this league holds. Draft opens when all have joined (${memberCount} of ${Number(maxMembersValue) || "?"} now).`
                      : `League size is locked after the draft opens (${memberCount} managers).`}
                  </Muted>
                </div>
              )}
              {tab === "pools" && (
                <LeaguePoolsEditor
                  value={poolsWithCounts}
                  onChange={setPools}
                  managerCapacity={managerCapacity}
                  structureEditable={league.status === "pre_draft"}
                  rosterClubOrder={rosterClubOrder}
                  onRosterClubOrderChange={setRosterClubOrder}
                  trailingAction={
                    <IconButton
                      type="submit"
                      label="Save league settings"
                      variant="primary"
                      busy={busy}
                      disabled={capacityErrors.length > 0}
                    >
                      <SaveIcon />
                    </IconButton>
                  }
                />
              )}
              {tab === "phases" && (
                <PhasesEditor
                  value={phases}
                  onChange={setPhases}
                  bonusTypeOptions={bonusTypeOptions}
                />
              )}
              {tab === "payouts" && (
                <div className="flex flex-col gap-4">
                  <Label className="max-w-xs">
                    Buy-in
                    <Input
                      type="number"
                      min={0}
                      step="0.01"
                      value={buyIn}
                      onChange={(e) => setBuyIn(e.target.value)}
                    />
                  </Label>
                  <PayoutsEditor
                    value={payouts}
                    onChange={setPayouts}
                    phaseOptions={phases.map((p) => ({
                      value: p.key,
                      label: p.label || p.key,
                    }))}
                  />
                </div>
              )}
            </div>

            {tab !== "pools" && (
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
            )}
          </form>
        )}
      </Stack>
    </Card>
  );
}

function ManagersInvitesPanel({
  league,
  invites,
  joinLink,
  joinLinkBusy = false,
  atOrOverCap,
  maxMembers,
  onInvite,
  onResendInvite,
  onRevoke,
  onJoinLinkUpdate,
  onToggleCommissioner,
  onRemove,
}: {
  league: League;
  invites?: Invite[];
  joinLink?: JoinLink;
  joinLinkBusy?: boolean;
  atOrOverCap: boolean;
  maxMembers: number | null;
  onInvite?: (e: FormEvent<HTMLFormElement>) => void;
  onResendInvite?: (id: UUID) => void;
  onRevoke?: (id: UUID) => void;
  onJoinLinkUpdate?: (body: { enabled?: boolean; rotate?: boolean }) => void | Promise<unknown>;
  onToggleCommissioner?: (memberId: UUID, isCommissioner: boolean) => void;
  onRemove?: (memberId: UUID) => void;
}) {
  const commissionerCount = league.members.filter((m) => m.is_commissioner).length;
  const preDraft = league.status === "pre_draft";
  const sorted = [...league.members].sort((a, b) => {
    const sa = a.draft_slot ?? Number.POSITIVE_INFINITY;
    const sb = b.draft_slot ?? Number.POSITIVE_INFINITY;
    if (sa !== sb) return sa - sb;
    return managerLabel(a).localeCompare(managerLabel(b));
  });
  const [copied, setCopied] = useState(false);
  const { toast } = useToast();
  const joinUrl =
    joinLink?.join_url ||
    (joinLink?.enabled && joinLink.token
      ? `${typeof location !== "undefined" ? location.origin : ""}/join?token=${encodeURIComponent(joinLink.token)}`
      : null);

  function canDemote(m: Manager) {
    return !(m.is_commissioner && commissionerCount <= 1);
  }

  function canRemove(m: Manager) {
    if (!preDraft) return false;
    const isSelf = m.id === league.current_member_id;
    if (isSelf && m.is_commissioner && commissionerCount <= 1) return false;
    return true;
  }

  async function copyJoinLink() {
    if (!joinUrl) return;
    try {
      await navigator.clipboard.writeText(joinUrl);
      setCopied(true);
      toast({ message: "Invite link copied", durationMs: 2000 });
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }

  return (
    <Stack>
      <div className="rounded-xl border border-line bg-surface-2/50 p-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <strong className="text-sm">Share join link</strong>
            <Muted className="mt-0.5 text-xs leading-snug">
              Anyone with this link can join your league.
            </Muted>
          </div>
          <label className="flex shrink-0 items-center gap-2">
            <Switch
              size="sm"
              checked={Boolean(joinLink?.enabled)}
              disabled={joinLinkBusy}
              onChange={(e) => onJoinLinkUpdate?.({ enabled: e.target.checked })}
            />
            <span className="text-xs font-semibold text-muted">
              {joinLinkBusy ? "Updating…" : joinLink?.enabled ? "Enabled" : "Disabled"}
            </span>
          </label>
        </div>
        {joinLink?.enabled && (
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            {joinUrl ? (
              <code className="min-w-0 flex-1 break-all rounded-lg border border-line bg-surface px-2.5 py-2 text-[0.7rem] text-muted">
                {joinUrl}
              </code>
            ) : (
              <div className="flex min-h-9 min-w-0 flex-1 items-center gap-2 rounded-lg border border-dashed border-line bg-surface px-2.5 py-2 text-xs font-semibold text-muted">
                <span
                  className="size-3.5 shrink-0 animate-spin rounded-full border-2 border-line border-t-brand"
                  aria-hidden
                />
                Generating link…
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <IconButton
                type="button"
                size="icon-sm"
                label={copied ? "Copied" : "Copy join link"}
                disabled={!joinUrl || joinLinkBusy}
                onClick={copyJoinLink}
              >
                <CopyIcon className="size-4" />
              </IconButton>
              <IconButton
                type="button"
                size="icon-sm"
                label="Rotate join link"
                busy={joinLinkBusy}
                onClick={() => {
                  if (
                    confirm(
                      "Rotate the join link? The current link will stop working.",
                    )
                  ) {
                    void onJoinLinkUpdate?.({ rotate: true });
                  }
                }}
              >
                <RefreshIcon className="size-4" />
              </IconButton>
            </div>
          </div>
        )}
      </div>

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
          {invites.map((i) => {
            const deliveries = i.email_deliveries || [];
            const latest = deliveries[0];
            return (
              <div
                className="flex flex-col gap-3 rounded-xl border border-line bg-surface-2/50 p-3"
                key={i.id}
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <strong className="break-all">{i.email}</strong>
                    <Muted>
                      {i.is_commissioner
                        ? "Commissioner"
                        : i.role === "member" || !i.role
                          ? "Manager"
                          : i.role.replaceAll("_", " ")}
                      {latest
                        ? ` · Last email ${latest.status}${
                            latest.created_at ? ` · ${formatDate(latest.created_at)}` : ""
                          }`
                        : ""}
                    </Muted>
                    {latest?.status !== "sent" && latest?.error && (
                      <Muted className="mt-0.5 break-words text-[0.7rem] text-danger">
                        {latest.error}
                      </Muted>
                    )}
                    {i.accept_url && i.status === "pending" && (
                      <Muted className="mt-0.5 break-all text-[0.7rem]">{i.accept_url}</Muted>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Status value={i.status} />
                    {i.status === "pending" && (
                      <>
                        <IconButton
                          type="button"
                          size="icon-sm"
                          label="Resend invite email"
                          onClick={() => onResendInvite?.(i.id)}
                        >
                          <SendIcon className="size-4" />
                        </IconButton>
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
                      </>
                    )}
                  </div>
                </div>
                {deliveries.length > 0 && (
                  <ul className="space-y-1 border-t border-line pt-2">
                    {deliveries.slice(0, 5).map((d) => (
                      <li key={d.id} className="text-[0.7rem] text-muted">
                        <span className="font-semibold text-ink/80">{d.status}</span>
                        {" · "}
                        {d.trigger}
                        {d.created_at ? ` · ${formatDate(d.created_at)}` : ""}
                        {d.error ? ` — ${d.error}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </Stack>
      )}
    </Stack>
  );
}
