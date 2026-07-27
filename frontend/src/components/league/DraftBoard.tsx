"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { DraftState, League, PoolTeam, Readiness } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { Empty, ErrorState, Loading, Status, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { CheckIcon, PlayIcon, RefreshIcon } from "@/components/ui/icons";
import { Card, Eyebrow, Muted, RankBadge, Row, Stack } from "@/components/ui/Card";
import { Label, Select } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import { ReadinessChecklist } from "@/components/ReadinessChecklist";
import { TeamCrest } from "./TeamCrest";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";
import { DraftAdminPanel } from "./DraftAdminPanel";
import { DraftSettingsSummary } from "./DraftSettingsSummary";

type DraftableTeam = PoolTeam & { pool_id: string; pool_label: string };
type DraftPhase = "pre" | "live" | "done";

function formatCountdown(ms: number): string {
  if (ms <= 0) return "0:00";
  const totalSec = Math.ceil(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function draftPhase(status: string | undefined, leagueStatus: string): DraftPhase {
  if (status === "complete" || status === "completed") return "done";
  if (status && ["running", "open"].includes(status)) return "live";
  if (status && ["pending", "paused", "cancelled"].includes(status)) return "pre";
  if (leagueStatus === "pre_draft") return "pre";
  if (leagueStatus === "drafting") return "live";
  return "done";
}

function PickClock({ deadlineAt }: { deadlineAt: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [deadlineAt]);
  const remaining = new Date(deadlineAt).getTime() - now;
  const expired = remaining <= 0;
  return (
    <StatusBanner tone={expired ? "error" : remaining < 15_000 ? "error" : "success"}>
      <strong>{expired ? "Time expired — auto-picking…" : "On the clock"}</strong>
      <div className="mt-1 font-mono text-2xl font-bold tabular-nums tracking-tight">
        {formatCountdown(remaining)}
      </div>
    </StatusBanner>
  );
}

export function DraftBoard({
  league,
  commissioner,
  onLeagueChange,
}: {
  league: League;
  commissioner: boolean;
  onLeagueChange?: () => void;
}) {
  /** Optional competition filter; empty string = all competitions. */
  const [poolFilter, setPoolFilter] = useState("");
  const [state, setState] = useState<DraftState>();
  const [teams, setTeams] = useState<DraftableTeam[]>([]);
  const [error, setError] = useState("");
  const [team, setTeam] = useState("");
  const [teamPoolId, setTeamPoolId] = useState("");
  const [busy, setBusy] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [readiness, setReadiness] = useState<Readiness>();
  const loadAbortRef = useRef<AbortController | null>(null);
  const leagueStatusRef = useRef(league.status);
  const onLeagueChangeRef = useRef(onLeagueChange);
  leagueStatusRef.current = league.status;
  onLeagueChangeRef.current = onLeagueChange;

  const multiPool = league.pools.length > 1;

  const managerName = (id: string) =>
    managerLabel(league.members.find((m) => m.id === id), "Unknown manager");

  const renderManagerName = (id: string) => (
    <ManagerLink leagueId={league.id} managerId={id}>
      {managerName(id)}
    </ManagerLink>
  );

  const crestByTeamId = useMemo(() => {
    const map = new Map<string, string | null>();
    for (const t of teams) map.set(t.id, t.crest_url);
    return map;
  }, [teams]);

  const availableTeams = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return teams
      .filter((t) => t.available)
      .filter((t) => !poolFilter || t.pool_id === poolFilter)
      .filter((t) => !q || t.name.toLowerCase().includes(q))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [teams, filter, poolFilter]);

  const load = useCallback(() => {
    if (!league.id) return;
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;
    const poolList = league.pools;
    Promise.all([
      api<DraftState>(`/leagues/${league.id}/draft`, { signal: controller.signal }),
      Promise.all(
        poolList.map(async (p) => {
          try {
            const poolTeams = await api<PoolTeam[]>(
              `/leagues/${league.id}/pools/${p.id}/teams`,
              { signal: controller.signal },
            );
            return poolTeams.map(
              (t): DraftableTeam => ({
                ...t,
                pool_id: p.id,
                pool_label: p.label || p.key,
              }),
            );
          } catch {
            return [] as DraftableTeam[];
          }
        }),
      ),
    ])
      .then(([draft, poolTeamLists]) => {
        if (controller.signal.aborted) return;
        setState(draft);
        setTeams(poolTeamLists.flat());
        setUpdatedAt(new Date());
        setError("");
        if (draft.league_status && draft.league_status !== leagueStatusRef.current) {
          onLeagueChangeRef.current?.();
        }
      })
      .catch((e) => {
        if (controller.signal.aborted || (e as Error)?.name === "AbortError") return;
        setError(errorMessage(e));
      });
    return () => {
      controller.abort();
      if (loadAbortRef.current === controller) loadAbortRef.current = null;
    };
  }, [league.id, league.pools]);

  useEffect(() => {
    setState(undefined);
    setTeam("");
    setFilter("");
    return load();
  }, [load]);

  const draftStatus = state?.status;
  const scheduledAt =
    state?.draft_scheduled_at ??
    league.draft_scheduled_at ??
    (typeof league.settings?.draft_scheduled_at === "string"
      ? league.settings.draft_scheduled_at
      : null);
  const pickTimerSeconds =
    state?.pick_timer_seconds ?? league.pick_timer_seconds ?? null;
  const scheduleOverdue =
    Boolean(scheduledAt) &&
    state?.status === "pending" &&
    new Date(scheduledAt as string).getTime() <= Date.now();

  useEffect(() => {
    const pendingWithSchedule = draftStatus === "pending" && Boolean(scheduledAt);
    if (
      !(draftStatus && ["running", "open"].includes(draftStatus)) &&
      !pendingWithSchedule
    ) {
      return;
    }
    const tick = () => {
      if (document.visibilityState === "hidden") return;
      load();
    };
    const id = window.setInterval(tick, 2500);
    return () => window.clearInterval(id);
  }, [draftStatus, scheduledAt, load]);

  const onClock = state?.current_member_id || state?.on_clock_member_id || null;
  const phase = draftPhase(state?.status, league.status);
  const running = phase === "live";
  const myTurn = Boolean(running && onClock === league.current_member_id);
  const selected =
    availableTeams.find((t) => t.id === team && t.pool_id === teamPoolId) ||
    teams.find((t) => t.id === team && t.pool_id === teamPoolId);
  const canOpenDraft = readiness?.ready === true;
  const showOpenControls =
    commissioner && state && ["pending", "paused", "cancelled"].includes(state.status);

  useEffect(() => {
    if (!showOpenControls) {
      setReadiness(undefined);
      return;
    }
    let cancelled = false;
    api<Readiness>(`/leagues/${league.id}/readiness`)
      .then((r) => {
        if (!cancelled) setReadiness(r);
      })
      .catch((e) => {
        if (cancelled) return;
        setReadiness({
          ready: false,
          checks: [
            {
              key: "load",
              label: "Could not load readiness",
              status: "error",
              detail: errorMessage(e),
            },
          ],
          errors: [errorMessage(e)],
          warnings: [],
        });
      });
    return () => {
      cancelled = true;
    };
  }, [
    showOpenControls,
    league.id,
    league.members.length,
    league.max_members,
    league.pools.length,
  ]);

  async function openDraft() {
    if (!canOpenDraft) {
      setError(readiness?.errors?.[0] || "League is not ready to open the draft.");
      return;
    }
    setBusy(true);
    try {
      setState(await api<DraftState>(`/leagues/${league.id}/draft/open`, json("POST")));
      setError("");
      onLeagueChange?.();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function pick(e: FormEvent) {
    e.preventDefault();
    if (!state || !team) return;
    setBusy(true);
    const key = pendingKey || crypto.randomUUID();
    setPendingKey(key);
    try {
      setState(
        await api<DraftState>(
          `/leagues/${league.id}/draft/picks`,
          json("POST", {
            team_id: team,
            ...(teamPoolId ? { pool_id: teamPoolId } : {}),
            idempotency_key: key,
            expected_version: state.version,
          }),
        ),
      );
      setTeam("");
      setTeamPoolId("");
      setPendingKey(null);
      load();
    } catch (err) {
      setError(errorMessage(err));
      load();
    } finally {
      setBusy(false);
    }
  }

  function renderPickHistory(opts?: { emptyTitle?: string; showOnClock?: boolean }) {
    if (!state) return null;
    const emptyTitle = opts?.emptyTitle ?? "No picks made";
    const showOnClock = opts?.showOnClock ?? false;
    return (
      <Card>
        <Stack>
          <Row between>
            <div>
              {phase === "done" ? (
                <>
                  <Eyebrow>Finished</Eyebrow>
                  <h2>Pick history</h2>
                </>
              ) : phase === "pre" ? (
                <>
                  <Eyebrow>Not started</Eyebrow>
                  <h2>Picks</h2>
                </>
              ) : (
                <>
                  <Eyebrow>Round {state.current_round}</Eyebrow>
                  <h2>Pick {state.current_pick_number}</h2>
                </>
              )}
            </div>
            <Status value={state.status} />
          </Row>
          {showOnClock && (
            <StatusBanner>
              <strong>On the clock: </strong>
              {onClock ? renderManagerName(onClock) : "Not started"}
            </StatusBanner>
          )}
          {!state.picks.length ? (
            <Empty title={emptyTitle} />
          ) : (
            <ul className="flex flex-col gap-2">
              {state.picks.map((p, i) => {
                const crest =
                  p.crest_url ??
                  (p.team_id ? crestByTeamId.get(p.team_id) : null) ??
                  null;
                return (
                  <li
                    className="flex items-center gap-3 rounded-xl border border-line bg-surface-2/50 p-3"
                    key={String(p.id || i)}
                  >
                    <RankBadge value={String(p.pick_number || i + 1)} />
                    <TeamCrest name={p.team_name} crestUrl={crest} size="md" />
                    <div className="min-w-0 flex-1">
                      <strong className="block truncate">
                        {p.team_id ? (
                          <TeamLink leagueId={league.id} teamId={p.team_id}>
                            {String(p.team_name || p.team_id || "Team")}
                          </TeamLink>
                        ) : (
                          String(p.team_name || "Team")
                        )}
                      </strong>
                      <Muted className="truncate">
                        {p.member_id
                          ? renderManagerName(String(p.member_id))
                          : "Unknown manager"}
                      </Muted>
                    </div>
                    <span className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-bold">
                      R{String(p.round_number || "—")}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Stack>
      </Card>
    );
  }

  function renderToolbar() {
    if (phase === "pre") return null;
    return (
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        {multiPool && phase === "live" ? (
          <Label className="min-w-0 w-full sm:max-w-xs sm:flex-1">
            Competition
            <Select value={poolFilter} onChange={(e) => setPoolFilter(e.target.value)}>
              <option value="">All competitions</option>
              {league.pools.map((p) => (
                <option value={p.id} key={p.id}>
                  {p.label}
                </option>
              ))}
            </Select>
          </Label>
        ) : (
          <div className="min-w-0 flex-1" />
        )}
        <div className="flex w-full items-center gap-2 sm:w-auto">
          {updatedAt && (
            <span className="hidden text-xs text-muted sm:inline" aria-live="polite">
              Updated {updatedAt.toLocaleTimeString()}
            </span>
          )}
          {state && (
            <IconButton type="button" variant="secondary" label="Refresh" onClick={load}>
              <RefreshIcon />
            </IconButton>
          )}
        </div>
      </div>
    );
  }

  function renderPreControls() {
    if (!showOpenControls && !scheduledAt && !pickTimerSeconds) return null;
    return (
      <Card>
        <Stack>
          <h2>Draft controls</h2>
          {scheduledAt && (
            <StatusBanner tone={scheduleOverdue ? "error" : undefined}>
              {scheduleOverdue ? (
                <>
                  <strong>Scheduled start has passed</strong>
                  <div className="mt-1">
                    Auto-open is waiting until all pre-draft checks pass (
                    {formatDate(scheduledAt)}).
                  </div>
                </>
              ) : (
                <>
                  <strong>Scheduled start</strong>
                  <div className="mt-1">{formatDate(scheduledAt)}</div>
                </>
              )}
            </StatusBanner>
          )}
          {pickTimerSeconds ? (
            <Muted className="text-xs">
              Pick timer: {pickTimerSeconds}s per pick (auto-picks a random available club
              when time runs out).
            </Muted>
          ) : null}
          {showOpenControls && (
            <>
              <Muted>
                Opens one league draft ({league.draft_style}
                {league.pools.length > 1
                  ? ") covering all competitions — managers pick clubs from any of them."
                  : ")."}
                {scheduledAt ? " You can still open manually once checks pass." : ""}
              </Muted>
              <ReadinessChecklist
                readiness={readiness}
                readyLabel={
                  scheduleOverdue
                    ? "Ready — will auto-open on the next check"
                    : "Ready to open"
                }
                readyWithWarningsDetail="warning(s) below — draft can open, but fix before relying on live scores."
                notReadyDetail={
                  scheduleOverdue
                    ? "issue(s) blocking auto-open — fix these and the draft will open automatically."
                    : "issue(s) to fix before opening the draft."
                }
                checksSummaryLabel="Pre-draft checks"
              />
              <div className="flex justify-start">
                <IconButton
                  type="button"
                  label="Open draft"
                  variant="primary"
                  busy={busy}
                  disabled={!canOpenDraft}
                  onClick={openDraft}
                >
                  <PlayIcon />
                </IconButton>
              </div>
            </>
          )}
        </Stack>
      </Card>
    );
  }

  function renderLiveControls() {
    if (!state) return null;
    return (
      <aside className="order-1 lg:order-2">
        <Card
          className={cn(
            myTurn && "ring-2 ring-brand/30",
            "lg:sticky lg:top-[calc(5rem+env(safe-area-inset-top))]",
          )}
        >
          <Stack>
            <h2>Draft controls</h2>
            {state.pick_deadline_at && <PickClock deadlineAt={state.pick_deadline_at} />}
            {!state.pick_deadline_at && pickTimerSeconds ? (
              <Muted className="text-xs">Pick timer is set; waiting for clock…</Muted>
            ) : null}
            {myTurn ? (
              <form className="flex flex-col gap-3" onSubmit={pick}>
                <Label>
                  Search teams
                  <input
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    placeholder="Filter by name…"
                    className="w-full min-h-11 rounded-xl border border-line bg-surface px-3.5 py-2.5 text-base text-ink"
                  />
                </Label>
                {selected && (
                  <div className="flex items-center gap-3 rounded-xl border border-brand/40 bg-brand/5 p-3">
                    <TeamCrest
                      name={selected.name}
                      crestUrl={selected.crest_url}
                      size="lg"
                    />
                    <div className="min-w-0">
                      <Muted className="text-xs">Selected</Muted>
                      <strong className="block truncate">{selected.name}</strong>
                      {multiPool && (
                        <Muted className="truncate text-xs">{selected.pool_label}</Muted>
                      )}
                    </div>
                  </div>
                )}
                <div
                  className="max-h-72 overflow-y-auto rounded-xl border border-line"
                  role="listbox"
                  aria-label="Available teams"
                >
                  {!availableTeams.length ? (
                    <Muted className="p-3 text-sm">No available teams match.</Muted>
                  ) : (
                    <ul className="divide-y divide-line">
                      {availableTeams.map((t) => (
                        <li key={`${t.pool_id}:${t.id}`}>
                          <button
                            type="button"
                            role="option"
                            aria-selected={team === t.id && teamPoolId === t.pool_id}
                            onClick={() => {
                              setTeam(t.id);
                              setTeamPoolId(t.pool_id);
                            }}
                            className={cn(
                              "flex w-full items-center gap-3 px-3 py-2.5 text-left transition",
                              team === t.id && teamPoolId === t.pool_id
                                ? "bg-brand/10"
                                : "bg-surface hover:bg-surface-2",
                            )}
                          >
                            <TeamCrest name={t.name} crestUrl={t.crest_url} size="md" />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-bold">
                                {t.name}
                              </span>
                              {multiPool && (
                                <Muted className="block truncate text-xs">
                                  {t.pool_label}
                                </Muted>
                              )}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="flex justify-start">
                  <IconButton
                    type="submit"
                    label="Make pick"
                    variant="primary"
                    busy={busy}
                    disabled={!team}
                  >
                    <CheckIcon />
                  </IconButton>
                </div>
              </form>
            ) : (
              <StatusBanner>
                Waiting for {onClock ? renderManagerName(onClock) : "the next manager"} to
                pick.
              </StatusBanner>
            )}
          </Stack>
        </Card>
      </aside>
    );
  }

  return (
    <Stack gap="md" className="animate-in">
      {renderToolbar()}

      {error && <ErrorState error={error} retry={load} />}

      {!state && !error ? (
        <Loading label="Loading draft" />
      ) : (
        state && (
          <>
            {phase === "pre" && (
              <Stack gap="md">
                <DraftSettingsSummary
                  league={league}
                  scheduledAt={scheduledAt}
                  pickTimerSeconds={pickTimerSeconds}
                />
                {renderPreControls()}
                {renderPickHistory({ emptyTitle: "Draft hasn’t started" })}
              </Stack>
            )}

            {phase === "live" && (
              <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
                {renderLiveControls()}
                <Stack gap="md" className="order-2 lg:order-1 min-w-0">
                  {renderPickHistory({ showOnClock: true })}
                  <DraftSettingsSummary
                    league={league}
                    scheduledAt={scheduledAt}
                    pickTimerSeconds={pickTimerSeconds}
                    onClockMemberId={onClock}
                    compact
                  />
                </Stack>
              </div>
            )}

            {phase === "done" && (
              <Stack gap="md">
                <StatusBanner tone="success">
                  <strong>Draft complete</strong>
                  <div className="mt-1">All picks are in. Rosters are locked in.</div>
                </StatusBanner>
                {renderPickHistory()}
                <DraftSettingsSummary
                  league={league}
                  scheduledAt={scheduledAt}
                  pickTimerSeconds={pickTimerSeconds}
                />
              </Stack>
            )}
          </>
        )
      )}

      {commissioner && (
        <Stack gap="sm">
          <h2 className="font-display text-lg font-extrabold">Commissioner tools</h2>
          <DraftAdminPanel
            league={league}
            onLeagueChange={() => {
              onLeagueChange?.();
              load();
            }}
          />
        </Stack>
      )}
    </Stack>
  );
}
