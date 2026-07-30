"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { DraftState, League, Readiness } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { formatDateTimeWithZone } from "@/lib/format";
import { fetchPoolTeams, type AnnotatedPoolTeam } from "@/lib/poolTeams";
import { Empty, ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { useLeagueContext } from "@/components/LeagueShell";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { CheckIcon, PlayIcon, RefreshIcon, SpinnerIcon } from "@/components/ui/icons";
import { Card, Eyebrow, Muted, RankBadge, Stack } from "@/components/ui/Card";
import { Label } from "@/components/ui/Field";
import { PoolFilterSelect } from "@/components/ui/PoolFilterSelect";
import { SurfaceListRow } from "@/components/ui/SurfaceListRow";
import { cn } from "@/lib/cn";
import { randomUUID } from "@/lib/randomUUID";
import { ReadinessChecklist } from "@/components/ReadinessChecklist";
import { TeamCrest } from "./TeamCrest";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";
import { DraftAdminPanel } from "./DraftAdminPanel";
import { DraftSettingsSummary } from "./DraftSettingsSummary";
import { DraftRoundBoard } from "./DraftRoundBoard";
import {
  DRAFT_PICK_SHEET_COLLAPSED_PAD,
  DraftPickSheet,
} from "./DraftPickSheet";

type DraftableTeam = AnnotatedPoolTeam;
type DraftPhase = "pre" | "live" | "done";

function draftPhase(status: string | undefined, leagueStatus: string): DraftPhase {
  if (status === "complete" || status === "completed") return "done";
  if (status && ["running", "open"].includes(status)) return "live";
  if (status && ["pending", "paused", "cancelled"].includes(status)) return "pre";
  if (leagueStatus === "pre_draft") return "pre";
  if (leagueStatus === "drafting") return "live";
  return "done";
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
  const leagueStatusRef = useRef(league.status);
  const onLeagueChangeRef = useRef(onLeagueChange);
  const poolsRef = useRef(league.pools);
  const draftReqIdRef = useRef(0);
  const teamsReqIdRef = useRef(0);
  const syncMetaRef = useRef({ version: -1, status: "", pickCount: -1 });
  const draftInflightRef = useRef(false);
  const draftQueuedRef = useRef(false);
  const draftQueuedForceTeamsRef = useRef(false);
  leagueStatusRef.current = league.status;
  onLeagueChangeRef.current = onLeagueChange;
  poolsRef.current = league.pools;

  const multiPool = league.pools.length > 1;
  const { subscribeDraftInvalidate } = useLeagueContext();

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

  const poolAvailableTeams = useMemo(() => {
    return teams
      .filter((t) => t.available)
      .filter((t) => !poolFilter || t.pool_id === poolFilter)
      .sort((a, b) => {
        const ao = a.draft_order;
        const bo = b.draft_order;
        if (ao != null && bo != null && ao !== bo) return ao - bo;
        if (ao != null && bo == null) return -1;
        if (ao == null && bo != null) return 1;
        return a.name.localeCompare(b.name);
      });
  }, [teams, poolFilter]);

  const availableTeams = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return poolAvailableTeams;
    return poolAvailableTeams.filter((t) => t.name.toLowerCase().includes(q));
  }, [poolAvailableTeams, filter]);

  const refreshTeams = useCallback(() => {
    if (!league.id) return;
    const reqId = ++teamsReqIdRef.current;
    fetchPoolTeams(league.id, poolsRef.current, { annotatePool: true })
      .then((poolTeams) => {
        if (reqId !== teamsReqIdRef.current) return;
        setTeams(poolTeams);
      })
      .catch(() => {
        /* keep prior board on transient pool errors */
      });
  }, [league.id]);

  const applyPicksToTeams = useCallback((draft: DraftState) => {
    const draftedIds = new Set(draft.picks.map((p) => p.team_id));
    setTeams((prev) => {
      if (!prev.length) return prev;
      let changed = false;
      const next = prev.map((t) => {
        const drafted = draftedIds.has(t.id);
        if (t.available === !drafted && t.drafted === drafted) return t;
        changed = true;
        return { ...t, available: !drafted, drafted };
      });
      return changed ? next : prev;
    });
  }, []);

  const applyDraft = useCallback(
    (draft: DraftState, opts?: { forceTeams?: boolean }) => {
      const prev = syncMetaRef.current;
      const picksChanged =
        draft.version !== prev.version ||
        draft.status !== prev.status ||
        draft.picks.length !== prev.pickCount;
      syncMetaRef.current = {
        version: draft.version,
        status: draft.status,
        pickCount: draft.picks.length,
      };
      setState(draft);
      setUpdatedAt(new Date());
      setError("");
      if (draft.league_status && draft.league_status !== leagueStatusRef.current) {
        onLeagueChangeRef.current?.();
      }
      // Full pool refetch only on first load / explicit refresh. Pick updates just
      // flip availability from the draft payload (draft_order is stable).
      if (opts?.forceTeams === true) {
        refreshTeams();
      } else if (picksChanged) {
        applyPicksToTeams(draft);
      }
    },
    [refreshTeams, applyPicksToTeams],
  );

  const refreshDraft = useCallback(
    (opts?: { forceTeams?: boolean }) => {
      if (!league.id) return;
      if (draftInflightRef.current) {
        draftQueuedRef.current = true;
        if (opts?.forceTeams) draftQueuedForceTeamsRef.current = true;
        return;
      }
      draftInflightRef.current = true;
      const reqId = ++draftReqIdRef.current;
      const forceTeams = opts?.forceTeams === true;
      api<DraftState>(`/leagues/${league.id}/draft`)
        .then((draft) => {
          if (reqId !== draftReqIdRef.current) return;
          applyDraft(draft, { forceTeams });
        })
        .catch((e) => {
          if (reqId !== draftReqIdRef.current) return;
          if ((e as Error)?.name === "AbortError") return;
          setError(errorMessage(e));
        })
        .finally(() => {
          if (reqId !== draftReqIdRef.current) return;
          draftInflightRef.current = false;
          if (draftQueuedRef.current) {
            const queuedForce = draftQueuedForceTeamsRef.current;
            draftQueuedRef.current = false;
            draftQueuedForceTeamsRef.current = false;
            refreshDraft({ forceTeams: queuedForce });
          }
        });
    },
    [league.id, applyDraft],
  );

  const load = useCallback(() => {
    refreshDraft({ forceTeams: true });
  }, [refreshDraft]);

  useEffect(() => {
    setState(undefined);
    setTeam("");
    setFilter("");
    syncMetaRef.current = { version: -1, status: "", pickCount: -1 };
    draftQueuedRef.current = false;
    draftQueuedForceTeamsRef.current = false;
    draftInflightRef.current = false;
    load();
    return () => {
      draftReqIdRef.current += 1;
      teamsReqIdRef.current += 1;
      draftInflightRef.current = false;
      draftQueuedRef.current = false;
      draftQueuedForceTeamsRef.current = false;
    };
  }, [load]);

  // Shared league live-sync (one Realtime channel + poll in LeagueShell).
  useEffect(() => {
    return subscribeDraftInvalidate((draft) => {
      // Drop any in-flight board fetch so it cannot overwrite this newer payload.
      draftReqIdRef.current += 1;
      draftInflightRef.current = false;
      draftQueuedRef.current = false;
      draftQueuedForceTeamsRef.current = false;
      applyDraft(draft);
    });
  }, [subscribeDraftInvalidate, applyDraft]);

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
      load();
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
    const key = pendingKey || randomUUID();
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

  function renderDraftBoardGrid() {
    if (!state) return null;
    return (
      <DraftRoundBoard
        league={league}
        picks={state.picks}
        currentPickNumber={state.current_pick_number}
        currentRound={state.current_round}
        onClockMemberId={onClock}
        crestByTeamId={crestByTeamId}
        yourTurn={myTurn}
        deadlineAt={state.pick_deadline_at}
        autopickPreview={state.autopick_preview}
      />
    );
  }

  function renderAvailablePickPanel(variant: "sidebar" | "sheet" = "sidebar") {
    if (!state) return null;
    const listMaxH = variant === "sheet" ? "max-h-[min(40vh,20rem)]" : "max-h-80";
    const list = (
      <div
        className={cn("overflow-y-auto rounded-xl border border-line", listMaxH)}
        role={myTurn ? "listbox" : undefined}
        aria-label="Available teams"
      >
        {!availableTeams.length ? (
          <Muted className="p-3 text-sm">No available teams match.</Muted>
        ) : (
          <ul className="divide-y divide-line">
            {availableTeams.map((t) => {
              const selectedRow = team === t.id && teamPoolId === t.pool_id;
              const body = (
                <>
                  <TeamCrest name={t.name} crestUrl={t.crest_url} size="md" />
                  <span className="flex min-w-0 flex-1 items-baseline gap-1.5">
                    <span className="truncate text-sm font-bold">{t.name}</span>
                    {multiPool && t.pool_label ? (
                      <Muted className="shrink-0 truncate text-xs">
                        · {t.pool_label}
                      </Muted>
                    ) : null}
                  </span>
                </>
              );
              return (
                <li key={`${t.pool_id}:${t.id}`}>
                  {myTurn ? (
                    <button
                      type="button"
                      role="option"
                      aria-selected={selectedRow}
                      onClick={() => {
                        setTeam(t.id);
                        setTeamPoolId(t.pool_id);
                      }}
                      className={cn(
                        "flex w-full items-center gap-3 px-3 py-2.5 text-left transition",
                        selectedRow ? "bg-brand/10" : "bg-surface hover:bg-surface-2",
                      )}
                    >
                      {body}
                    </button>
                  ) : (
                    <div className="flex items-center gap-3 px-3 py-2.5">{body}</div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    );

    const body = (
      <Stack className="min-w-0" gap={variant === "sheet" ? "sm" : "md"}>
        <div>
          <Eyebrow>
            {poolAvailableTeams.length} left
            {filter.trim() && availableTeams.length !== poolAvailableTeams.length
              ? ` · ${availableTeams.length} shown`
              : ""}
          </Eyebrow>
          {variant === "sidebar" || myTurn ? (
            <h2 className={cn(variant === "sheet" && "text-base")}>
              {myTurn ? "Pick a team" : "Available teams"}
            </h2>
          ) : null}
        </div>

        {!myTurn && (
          <StatusBanner>
            Waiting for {onClock ? renderManagerName(onClock) : "the next manager"} to
            pick.
          </StatusBanner>
        )}

        <div
          className={cn(
            "grid gap-3",
            multiPool && variant === "sidebar" && "sm:grid-cols-[minmax(0,12rem)_1fr]",
          )}
        >
          {multiPool && (
            <Label className="min-w-0">
              Competition
              <PoolFilterSelect
                pools={league.pools}
                value={poolFilter}
                onChange={(value) => {
                  setPoolFilter(value);
                  if (value && teamPoolId && teamPoolId !== value) {
                    setTeam("");
                    setTeamPoolId("");
                  }
                }}
              />
            </Label>
          )}
          <Label className="min-w-0">
            Search teams
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by name…"
              className="w-full min-h-11 rounded-xl border border-line bg-surface px-3.5 py-2.5 text-base text-ink"
            />
          </Label>
        </div>

        {myTurn ? (
          <form className="flex flex-col gap-3" onSubmit={pick}>
            {list}
            {selected && (
              <div className="flex items-center gap-3 rounded-xl border border-brand/40 bg-brand/5 p-3">
                <TeamCrest
                  name={selected.name}
                  crestUrl={selected.crest_url}
                  size="lg"
                />
                <div className="min-w-0">
                  <Muted className="text-xs">Selected</Muted>
                  <strong className="flex min-w-0 items-baseline gap-1.5">
                    <span className="truncate">{selected.name}</span>
                    {multiPool && selected.pool_label ? (
                      <Muted className="shrink-0 truncate text-xs font-normal">
                        · {selected.pool_label}
                      </Muted>
                    ) : null}
                  </strong>
                </div>
              </div>
            )}
            <div className="flex justify-start">
              <Button type="submit" variant="primary" disabled={!team || busy}>
                {busy ? <SpinnerIcon className="size-5" /> : <CheckIcon />}
                Draft team
              </Button>
            </div>
          </form>
        ) : (
          list
        )}
      </Stack>
    );

    if (variant === "sheet") {
      return <div className="min-w-0">{body}</div>;
    }

    return (
      <Card
        className={cn(
          "min-w-0 max-w-full overflow-hidden",
          myTurn && "draft-on-clock-pulse bg-brand/[0.04]",
        )}
      >
        {body}
      </Card>
    );
  }

  function renderPickHistory(opts?: { emptyTitle?: string }) {
    if (!state) return null;
    const emptyTitle = opts?.emptyTitle ?? "No picks made";
    return (
      <Card>
        <Stack>
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
                  <SurfaceListRow
                    as="li"
                    className="flex items-center gap-3"
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
                  </SurfaceListRow>
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
      <div className="flex items-center justify-end gap-2">
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
    );
  }

  function renderPreControls() {
    if (!commissioner) return null;
    if (!showOpenControls && !(scheduledAt && scheduleOverdue)) return null;
    return (
      <Card>
        <Stack>
          <h2>Draft controls</h2>
          {scheduledAt && scheduleOverdue && (
            <StatusBanner tone="error">
              <strong>Scheduled start has passed</strong>
              <div className="mt-1">
                Auto-open is waiting until all pre-draft checks pass (
                {formatDateTimeWithZone(scheduledAt)}).
              </div>
            </StatusBanner>
          )}
          {showOpenControls && (
            <>
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

  return (
    <Stack
      gap="md"
      className={cn("animate-in", phase === "live" && DRAFT_PICK_SHEET_COLLAPSED_PAD)}
    >
      {renderToolbar()}

      {error && <ErrorState error={error} retry={load} />}

      {!state && !error ? (
        <Loading label="Loading draft" />
      ) : (
        state && (
          <>
            {phase === "pre" && (
              <Stack gap="md">
                {!commissioner && (
                  <DraftSettingsSummary
                    league={league}
                    scheduledAt={scheduledAt}
                    pickTimerSeconds={pickTimerSeconds}
                  />
                )}
                {renderPreControls()}
                {state.picks.length > 0 &&
                  renderPickHistory({ emptyTitle: "Draft hasn’t started" })}
              </Stack>
            )}

            {phase === "live" && (
              <div className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-3 lg:items-start">
                <div className="min-w-0 lg:col-span-2">{renderDraftBoardGrid()}</div>
                <div className="hidden min-w-0 lg:sticky lg:top-4 lg:col-span-1 lg:block">
                  {renderAvailablePickPanel("sidebar")}
                </div>
                <DraftPickSheet
                  yourTurn={myTurn}
                  deadlineAt={state.pick_deadline_at}
                  autopickPreview={state.autopick_preview}
                >
                  {renderAvailablePickPanel("sheet")}
                </DraftPickSheet>
              </div>
            )}

            {phase === "done" && (
              <Stack gap="md">
                <StatusBanner tone="success">
                  <strong>Draft complete</strong>
                  <div className="mt-1">All picks are in. Rosters are locked in.</div>
                </StatusBanner>
                {renderDraftBoardGrid()}
                {!commissioner && (
                  <DraftSettingsSummary
                    league={league}
                    scheduledAt={scheduledAt}
                    pickTimerSeconds={pickTimerSeconds}
                  />
                )}
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
            draftVersion={state?.version}
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
