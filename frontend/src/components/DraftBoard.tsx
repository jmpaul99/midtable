"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { DraftState, League, PoolTeam } from "@/lib/types";
import { Empty, ErrorState, Loading, Status } from "./State";

export function DraftBoard({ league, commissioner }: { league: League; commissioner: boolean }) {
  const [poolId, setPoolId] = useState(league.pools[0]?.id || "");
  const [state, setState] = useState<DraftState>();
  const [teams, setTeams] = useState<PoolTeam[]>([]);
  const [error, setError] = useState("");
  const [team, setTeam] = useState("");
  const [busy, setBusy] = useState(false);

  const memberName = (id: string) =>
    league.members.find((m) => m.id === id)?.display_name || "Unknown manager";

  const load = useCallback(() => {
    if (!poolId) return;
    Promise.all([
      api<DraftState>(`/pools/${poolId}/draft`),
      api<PoolTeam[]>(`/pools/${poolId}/teams`),
    ])
      .then(([draft, poolTeams]) => {
        setState(draft);
        setTeams(poolTeams);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [poolId]);

  useEffect(() => {
    setState(undefined);
    setError("");
    load();
  }, [load]);

  async function start(format: "linear" | "snake") {
    setBusy(true);
    try {
      setState(await api<DraftState>(`/pools/${poolId}/draft/start`, json("POST", { format })));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function pick(e: FormEvent) {
    e.preventDefault();
    if (!state) return;
    setBusy(true);
    try {
      setState(
        await api<DraftState>(
          `/pools/${poolId}/draft/picks`,
          json("POST", {
            team_id: team,
            idempotency_key: crypto.randomUUID(),
            expected_version: state.version,
          }),
        ),
      );
      setTeams((current) =>
        current.map((item) =>
          item.id === team ? { ...item, available: false, drafted: true } : item,
        ),
      );
      setTeam("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="row between">
        <label>
          Pool
          <select value={poolId} onChange={(e) => setPoolId(e.target.value)}>
            {league.pools.map((p) => (
              <option value={p.id} key={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {state && (
          <button type="button" className="secondary" onClick={load}>
            Refresh board
          </button>
        )}
      </div>

      {error && <ErrorState error={error} retry={load} />}

      {!state && !error ? (
        <Loading label="Loading draft" />
      ) : (
        state && (
          <div className="draft-board">
            <section className="panel stack">
              <div className="row between">
                <div>
                  <p className="eyebrow">Round {state.current_round}</p>
                  <h2>Pick {state.current_pick_number}</h2>
                </div>
                <Status value={state.status} />
              </div>
              {state.status !== "completed" && (
                <div className="notice">
                  <strong>On the clock: </strong>
                  {state.current_member_id ? memberName(state.current_member_id) : "Not started"}
                </div>
              )}
              {!state.picks.length ? (
                <Empty title="No picks made" />
              ) : (
                <div>
                  {state.picks.map((p, i) => (
                    <div className="pick" key={String(p.id || i)}>
                      <span className="rank">{String(p.pick_number || i + 1)}</span>
                      <div>
                        <strong>{String(p.team_name || p.team_id || "Team")}</strong>
                        <div className="muted">{memberName(String(p.member_id || ""))}</div>
                      </div>
                      <span className="pill">R{String(p.round_number || "—")}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <aside className="panel stack">
              <h2>Draft controls</h2>
              {commissioner && ["pending", "paused", "cancelled"].includes(state.status) && (
                <>
                  <p className="muted">Start this board after setting the order in Admin.</p>
                  <div className="row">
                    <button type="button" disabled={busy} onClick={() => start("linear")}>
                      Start linear
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      className="secondary"
                      onClick={() => start("snake")}
                    >
                      Start snake
                    </button>
                  </div>
                </>
              )}
              {state.status === "running" &&
                (state.current_member_id === league.current_member_id ? (
                  <form className="stack" onSubmit={pick}>
                    <label>
                      Available team
                      <select required value={team} onChange={(e) => setTeam(e.target.value)}>
                        <option value="">Choose…</option>
                        {teams
                          .filter((t) => t.available)
                          .map((t) => (
                            <option value={t.id} key={t.id}>
                              {t.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <button type="submit" disabled={busy || !team}>
                      {busy ? "Submitting…" : "Make pick"}
                    </button>
                  </form>
                ) : (
                  <div className="notice">
                    Waiting for{" "}
                    {state.current_member_id
                      ? memberName(state.current_member_id)
                      : "the next manager"}{" "}
                    to pick.
                  </div>
                ))}
            </aside>
          </div>
        )
      )}
    </div>
  );
}
