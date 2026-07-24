"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { DraftState, League, PoolTeam } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { Empty, ErrorState, Loading, Status, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { CheckIcon, PlayIcon, RefreshIcon } from "@/components/ui/icons";
import { Card, Eyebrow, Muted, RankBadge, Row, Stack } from "@/components/ui/Card";
import { Label, Select } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import { TeamCrest } from "./TeamCrest";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";
import { DraftAdminPanel } from "./DraftAdminPanel";

export function DraftBoard({
  league,
  commissioner,
  onLeagueChange,
}: {
  league: League;
  commissioner: boolean;
  onLeagueChange?: () => void;
}) {
  const [poolId, setPoolId] = useState(league.pools[0]?.id || "");
  const [state, setState] = useState<DraftState>();
  const [teams, setTeams] = useState<PoolTeam[]>([]);
  const [error, setError] = useState("");
  const [team, setTeam] = useState("");
  const [busy, setBusy] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const loadAbortRef = useRef<AbortController | null>(null);

  const managerName = (id: string) =>
    managerLabel(league.members.find((m) => m.id === id), "Unknown manager");

  const ManagerName = ({ id }: { id: string }) => (
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
      .filter((t) => !q || t.name.toLowerCase().includes(q))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [teams, filter]);

  const load = useCallback(() => {
    if (!league.id) return;
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;
    const teamsPath = poolId ? `/leagues/${league.id}/pools/${poolId}/teams` : null;
    Promise.all([
      api<DraftState>(`/leagues/${league.id}/draft`, { signal: controller.signal }),
      teamsPath
        ? api<PoolTeam[]>(teamsPath, { signal: controller.signal })
        : Promise.resolve([] as PoolTeam[]),
    ])
      .then(([draft, poolTeams]) => {
        if (controller.signal.aborted) return;
        setState(draft);
        setTeams(poolTeams);
        setUpdatedAt(new Date());
        setError("");
      })
      .catch((e) => {
        if (controller.signal.aborted || (e as Error)?.name === "AbortError") return;
        setError(errorMessage(e));
      });
    return () => {
      controller.abort();
      if (loadAbortRef.current === controller) loadAbortRef.current = null;
    };
  }, [league.id, poolId]);

  useEffect(() => {
    setState(undefined);
    setTeam("");
    setFilter("");
    return load();
  }, [load]);

  const draftStatus = state?.status;
  useEffect(() => {
    if (!draftStatus || !["running", "open"].includes(draftStatus)) return;
    const tick = () => {
      if (document.visibilityState === "hidden") return;
      load();
    };
    const id = window.setInterval(tick, 2500);
    return () => window.clearInterval(id);
  }, [draftStatus, load]);

  const onClock = state?.current_member_id || state?.on_clock_member_id || null;
  const running = state && ["running", "open"].includes(state.status);
  const myTurn = Boolean(running && onClock === league.current_member_id);
  const selected = teams.find((t) => t.id === team);
  const requiredManagers = league.max_members ?? null;
  const joinedManagers = league.members.length;
  const rosterFull =
    requiredManagers != null && joinedManagers === requiredManagers;
  const canOpenDraft = rosterFull;

  async function openDraft() {
    if (!canOpenDraft) {
      setError(
        requiredManagers == null
          ? "Set the required number of managers in league settings before opening the draft."
          : `Need exactly ${requiredManagers} managers to open the draft (have ${joinedManagers}).`,
      );
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
            idempotency_key: key,
            expected_version: state.version,
          }),
        ),
      );
      setTeam("");
      setPendingKey(null);
      load();
    } catch (err) {
      setError(errorMessage(err));
      load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Stack gap="md" className="animate-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <Label className="min-w-0 w-full sm:max-w-xs sm:flex-1">
          Competition
          <Select value={poolId} onChange={(e) => setPoolId(e.target.value)}>
            {league.pools.map((p) => (
              <option value={p.id} key={p.id}>
                {p.name || p.label}
              </option>
            ))}
          </Select>
        </Label>
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

      {error && <ErrorState error={error} retry={load} />}

      {!state && !error ? (
        <Loading label="Loading draft" />
      ) : (
        state && (
          <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
            <aside className="order-1 lg:order-2">
              <Card
                className={cn(
                  myTurn && "ring-2 ring-brand/30",
                  "lg:sticky lg:top-[calc(5rem+env(safe-area-inset-top))]",
                )}
              >
                <Stack>
                  <h2>Draft controls</h2>
                  {commissioner && ["pending", "paused", "cancelled"].includes(state.status) && (
                    <>
                      <Muted>
                        Opens the league draft using the league draft style ({league.draft_style}).
                      </Muted>
                      {requiredManagers == null ? (
                        <StatusBanner tone="error">
                          Set the required number of managers in league settings before opening
                          the draft.
                        </StatusBanner>
                      ) : joinedManagers < requiredManagers ? (
                        <StatusBanner tone="error">
                          {joinedManagers} of {requiredManagers} managers joined. Invite the rest
                          before opening the draft.
                        </StatusBanner>
                      ) : joinedManagers > requiredManagers ? (
                        <StatusBanner tone="error">
                          {joinedManagers} of {requiredManagers} managers joined. Remove extras
                          before opening the draft.
                        </StatusBanner>
                      ) : (
                        <StatusBanner tone="success">
                          Roster full ({joinedManagers}/{requiredManagers}). Ready to open.
                        </StatusBanner>
                      )}
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
                  {running &&
                    (myTurn ? (
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
                                <li key={t.id}>
                                  <button
                                    type="button"
                                    role="option"
                                    aria-selected={team === t.id}
                                    onClick={() => setTeam(t.id)}
                                    className={cn(
                                      "flex w-full items-center gap-3 px-3 py-2.5 text-left transition",
                                      team === t.id
                                        ? "bg-brand/10"
                                        : "bg-surface hover:bg-surface-2",
                                    )}
                                  >
                                    <TeamCrest name={t.name} crestUrl={t.crest_url} size="md" />
                                    <span className="min-w-0 flex-1 truncate text-sm font-bold">
                                      {t.name}
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
                        Waiting for {onClock ? <ManagerName id={onClock} /> : "the next manager"} to pick.
                      </StatusBanner>
                    ))}
                </Stack>
              </Card>
            </aside>

            <Card className="order-2 lg:order-1">
              <Stack>
                <Row between>
                  <div>
                    <Eyebrow>Round {state.current_round}</Eyebrow>
                    <h2>Pick {state.current_pick_number}</h2>
                  </div>
                  <Status value={state.status} />
                </Row>
                {state.status !== "complete" && state.status !== "completed" && (
                  <StatusBanner>
                    <strong>On the clock: </strong>
                    {onClock ? <ManagerName id={onClock} /> : "Not started"}
                  </StatusBanner>
                )}
                {!state.picks.length ? (
                  <Empty title="No picks made" />
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
                          <TeamCrest
                            name={p.team_name}
                            crestUrl={crest}
                            size="md"
                          />
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
                              {p.member_id ? (
                                <ManagerName id={String(p.member_id)} />
                              ) : (
                                "Unknown manager"
                              )}
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
          </div>
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
