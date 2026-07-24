"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDate, formatNumber, json } from "@/lib/api";
import type {
  Bonus,
  DraftState,
  Invite,
  League,
  MatchEvent,
  PoolTeam,
  Readiness,
  SyncStatus,
  UUID,
} from "@/lib/types";
import { Empty, ErrorState, JsonEditor, Loading, Status } from "./State";

export function AdminPanel({ league }: { league: League }) {
  const [invites, setInvites] = useState<Invite[]>();
  const [bonuses, setBonuses] = useState<Bonus[]>();
  const [matches, setMatches] = useState<MatchEvent[]>([]);
  const [sync, setSync] = useState<SyncStatus[]>();
  const [poolTeams, setPoolTeams] = useState<Record<string, PoolTeam[]>>({});
  const [drafts, setDrafts] = useState<Record<string, DraftState>>({});
  const [readiness, setReadiness] = useState<Readiness>();
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [provider, setProvider] = useState<Record<string, unknown>>(league.provider_params);
  const [orderPool, setOrderPool] = useState(league.pools[0]?.id || "");
  const [draftOrder, setDraftOrder] = useState<UUID[]>(
    league.pools[0]?.draft_order || league.members.map((m) => m.id),
  );
  const [teamPool, setTeamPool] = useState(league.pools[0]?.id || "");
  const [pickPool, setPickPool] = useState("");

  const load = useCallback(() => {
    Promise.all([
      api<Invite[]>(`/leagues/${league.id}/invites`),
      api<Bonus[]>(`/leagues/${league.id}/bonuses`),
      api<MatchEvent[]>(`/leagues/${league.id}/match-log`),
      api<SyncStatus[]>(`/leagues/${league.id}/sync-status`),
      api<Readiness>(`/leagues/${league.id}/readiness`),
      Promise.all(
        league.pools.map(async (p) => [p.id, await api<PoolTeam[]>(`/pools/${p.id}/teams`)] as const),
      ),
      Promise.all(
        league.pools.map(
          async (p) => [p.id, await api<DraftState>(`/pools/${p.id}/draft`)] as const,
        ),
      ),
    ])
      .then(([a, b, matchEvents, c, d, teams, draftStates]) => {
        setInvites(a);
        setBonuses(b);
        setMatches(matchEvents);
        setSync(c);
        setReadiness(d);
        setPoolTeams(Object.fromEntries(teams));
        setDrafts(Object.fromEntries(draftStates));
      })
      .catch((e) => setError(errorMessage(e)));
  }, [league.id, league.pools]);

  useEffect(() => {
    load();
  }, [load]);

  async function action(path: string, method: string, body?: unknown) {
    setError("");
    setMessage("");
    try {
      const out = await api<{ detail?: string; status?: string }>(path, json(method, body));
      setMessage(out?.detail || out?.status || "Saved.");
      load();
      return out;
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function invite(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const out = await action(`/leagues/${league.id}/invites`, "POST", {
      email: f.get("email"),
      commissioner: f.get("commissioner") === "on",
      expires_in_hours: Number(f.get("hours")),
    });
    if (out && (out as unknown as Invite).token) {
      const token = (out as unknown as Invite).token;
      setMessage(
        `Invite created: ${location.origin}/invites/accept?token=${encodeURIComponent(token || "")}`,
      );
    }
  }

  function changeOrderPool(id: string) {
    setOrderPool(id);
    setDraftOrder(
      league.pools.find((p) => p.id === id)?.draft_order || league.members.map((m) => m.id),
    );
  }

  function moveMember(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= draftOrder.length) return;
    const next = [...draftOrder];
    [next[index], next[target]] = [next[target], next[index]];
    setDraftOrder(next);
  }

  async function preassign(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await action(`/pools/${f.get("pool")}/preassignments`, "POST", {
      member_id: f.get("member"),
      team_id: f.get("team"),
      slot_number: Number(f.get("slot")),
      keeper: f.get("keeper") === "on",
    });
  }

  async function bonus(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await action(`/leagues/${league.id}/bonuses`, "POST", {
      team_id: f.get("team"),
      match_id: f.get("match") || null,
      bonus_type: f.get("type"),
      phase: f.get("phase") || "overall",
      points: Number(f.get("points")),
      reason: f.get("reason"),
    });
  }

  const allTeams = league.pools.flatMap((pool) =>
    (poolTeams[pool.id] || []).map((team) => ({ team, pool })),
  );
  const allPicks = league.pools.flatMap((pool) =>
    (drafts[pool.id]?.picks || [])
      .filter((pick) => pick.id)
      .map((pick) => ({ pick, pool })),
  );
  const matchOptions = Array.from(
    new Map(matches.map((match) => [match.match_id, match])).values(),
  );

  return (
    <div className="stack">
      {error && <ErrorState error={error} />}
      {message && <div className="notice code">{message}</div>}

      <div className="grid grid-2">
        <section className="panel stack">
          <h2>Invitations</h2>
          <form className="form-grid" onSubmit={invite}>
            <label>
              Email
              <input type="email" name="email" required />
            </label>
            <label>
              Expires (hours)
              <input type="number" name="hours" min={1} max={2160} defaultValue={168} />
            </label>
            <label className="row">
              <input style={{ width: "auto" }} type="checkbox" name="commissioner" />
              Commissioner access
            </label>
            <button className="full" type="submit">
              Create invite
            </button>
          </form>
          <div className="stack">
            {invites?.map((i) => (
              <div className="row between panel inset" key={i.id}>
                <div>
                  <strong>{i.email}</strong>
                  <div className="muted">
                    {i.role} · expires {formatDate(i.expires_at)}
                  </div>
                </div>
                <div className="row">
                  <Status value={i.status} />
                  {i.status === "pending" && (
                    <button
                      type="button"
                      className="danger"
                      onClick={() => action(`/leagues/${league.id}/invites/${i.id}`, "DELETE")}
                    >
                      Revoke
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel stack">
          <h2>Readiness &amp; sync</h2>
          {readiness ? (
            <div className={`notice ${readiness.ready ? "" : "error"}`}>
              <strong>{readiness.ready ? "Ready to score" : "Setup incomplete"}</strong>
              {[...readiness.errors, ...readiness.warnings].map((x) => (
                <div key={x}>{x}</div>
              ))}
            </div>
          ) : (
            <Loading />
          )}
          <JsonEditor
            label="League provider parameters"
            value={provider}
            onChange={(v) => setProvider(v as Record<string, unknown>)}
          />
          <div className="row">
            <button
              type="button"
              className="secondary"
              onClick={() =>
                action(`/leagues/${league.id}/provider-params`, "PUT", {
                  league: provider,
                  pools: {},
                })
              }
            >
              Save parameters
            </button>
            <button
              type="button"
              onClick={() =>
                action(`/leagues/${league.id}/bootstrap`, "POST", {
                  provider_params: provider,
                })
              }
            >
              Bootstrap
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() =>
                action(`/leagues/${league.id}/sync`, "POST", {
                  date_from: null,
                  date_to: null,
                  statuses: [],
                })
              }
            >
              Sync now
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => action(`/leagues/${league.id}/recompute`, "POST")}
            >
              Recompute
            </button>
          </div>
          {sync?.map((s) => (
            <div className="panel inset" key={s.id}>
              <div className="row between">
                <strong>{s.resource_type}</strong>
                <Status value={s.status} />
              </div>
              <small className="muted">
                Last success {formatDate(s.last_success_at)} · quota{" "}
                {s.rate_limit_remaining ?? "—"} · reset {formatDate(s.rate_limit_reset_at)}
              </small>
              {s.last_error && <div className="notice error">{s.last_error}</div>}
            </div>
          ))}
        </section>
      </div>

      <div className="grid grid-2">
        <section className="panel stack">
          <h2>Draft order &amp; keepers</h2>
          <label>
            Pool
            <select value={orderPool} onChange={(e) => changeOrderPool(e.target.value)}>
              {league.pools.map((p) => (
                <option value={p.id} key={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <div className="stack">
            {draftOrder.map((id, index) => (
              <div className="row panel inset" key={id}>
                <span className="rank">{index + 1}</span>
                <strong style={{ flex: 1 }}>
                  {league.members.find((m) => m.id === id)?.display_name || id}
                </strong>
                <button
                  type="button"
                  className="secondary"
                  aria-label="Move up"
                  disabled={index === 0}
                  onClick={() => moveMember(index, -1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="secondary"
                  aria-label="Move down"
                  disabled={index === draftOrder.length - 1}
                  onClick={() => moveMember(index, 1)}
                >
                  ↓
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() =>
              action(`/pools/${orderPool}/draft-order`, "PUT", { member_ids: draftOrder })
            }
          >
            Save draft order
          </button>
          <form className="form-grid" onSubmit={preassign}>
            <label>
              Pool
              <select
                name="pool"
                value={teamPool}
                onChange={(e) => setTeamPool(e.target.value)}
              >
                {league.pools.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Member
              <select name="member">
                {league.members.map((m) => (
                  <option value={m.id} key={m.id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Available team
              <select name="team" required>
                <option value="">Choose…</option>
                {(poolTeams[teamPool] || [])
                  .filter((t) => t.available)
                  .map((t) => (
                    <option value={t.id} key={t.id}>
                      {t.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Slot
              <input name="slot" type="number" min={1} required />
            </label>
            <label className="row">
              <input style={{ width: "auto" }} type="checkbox" name="keeper" />
              Keeper
            </label>
            <button className="full" type="submit">
              Preassign team
            </button>
          </form>
        </section>

        <section className="panel stack">
          <h2>Corrections</h2>
          <details>
            <summary>Roster correction</summary>
            <form
              className="form-grid"
              style={{ marginTop: "0.8rem" }}
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void action(`/leagues/${league.id}/roster-corrections`, "POST", {
                  member_id: f.get("member"),
                  team_id: f.get("team"),
                  slot_number: Number(f.get("slot")),
                  reason: f.get("reason"),
                });
              }}
            >
              <label>
                Member
                <select name="member">
                  {league.members.map((m) => (
                    <option value={m.id} key={m.id}>
                      {m.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Team
                <select name="team" required>
                  <option value="">Choose…</option>
                  {allTeams.map(({ team, pool }) => (
                    <option value={team.id} key={`${pool.id}-${team.id}`}>
                      {team.name} · {pool.name}
                      {team.current_owner ? ` · ${team.current_owner.display_name}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Slot
                <input name="slot" type="number" min={1} required />
              </label>
              <label>
                Reason
                <input name="reason" minLength={3} required />
              </label>
              <button className="full" type="submit">
                Correct roster
              </button>
            </form>
          </details>
          <details>
            <summary>Pick correction</summary>
            <form
              className="form-grid"
              style={{ marginTop: "0.8rem" }}
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void action(`/leagues/${league.id}/pick-corrections`, "POST", {
                  pick_id: f.get("pick"),
                  team_id: f.get("team"),
                  reason: f.get("reason"),
                });
              }}
            >
              <label>
                Draft pick
                <select
                  name="pick"
                  required
                  onChange={(e) =>
                    setPickPool(
                      allPicks.find(({ pick }) => pick.id === e.target.value)?.pool.id || "",
                    )
                  }
                >
                  <option value="">Choose…</option>
                  {allPicks.map(({ pick, pool }) => (
                    <option value={pick.id} key={pick.id}>
                      {pool.name} · pick {pick.pick_number} · {pick.team_name || "Team"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Available replacement
                <select name="team" required disabled={!pickPool}>
                  <option value="">Choose…</option>
                  {allTeams
                    .filter(({ team, pool }) => team.available && pool.id === pickPool)
                    .map(({ team, pool }) => (
                      <option value={team.id} key={`${pool.id}-${team.id}`}>
                        {team.name}
                      </option>
                    ))}
                </select>
              </label>
              <label className="full">
                Reason
                <input name="reason" minLength={3} required />
              </label>
              <button className="full" type="submit" disabled={!allPicks.length}>
                Correct pick
              </button>
            </form>
          </details>
        </section>
      </div>

      <section className="panel stack">
        <h2>Manual bonuses</h2>
        <form className="form-grid" onSubmit={bonus}>
          <label>
            Team
            <select name="team" required>
              <option value="">Choose…</option>
              {allTeams.map(({ team, pool }) => (
                <option value={team.id} key={`${pool.id}-${team.id}`}>
                  {team.name} · {pool.name}
                  {team.current_owner
                    ? ` · ${team.current_owner.display_name}`
                    : " · unowned"}
                </option>
              ))}
            </select>
          </label>
          <label>
            Bonus type
            <select name="type" required>
              <option value="">Choose…</option>
              {league.bonus_type_keys.map((key) => (
                <option value={key} key={key}>
                  {key}
                </option>
              ))}
            </select>
          </label>
          <label>
            Points
            <input name="points" type="number" step="0.01" required />
          </label>
          <label>
            Phase
            <select name="phase" defaultValue="overall">
              <option value="overall">overall</option>
              {league.phases.map((p) => (
                <option value={p.key} key={p.key}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Match <span className="muted">(optional)</span>
            <select name="match">
              <option value="">Season-level bonus</option>
              {matchOptions.map((match) => (
                <option value={match.match_id} key={match.match_id}>
                  {formatDate(match.kickoff_at)} · MW {match.matchday} · {match.team_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Reason
            <input name="reason" required />
          </label>
          <button className="full" type="submit">
            Award bonus
          </button>
        </form>
        {bonuses?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Current owner</th>
                  <th>Points</th>
                  <th>Reason</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {bonuses.map((b) => (
                  <tr key={b.id}>
                    <td>{b.bonus_type}</td>
                    <td>{b.display_name || "Unowned"}</td>
                    <td>{formatNumber(b.points)}</td>
                    <td>{b.reason}</td>
                    <td>
                      {!b.revoked_at && (
                        <button
                          type="button"
                          className="danger"
                          onClick={() =>
                            action(`/leagues/${league.id}/bonuses/${b.id}`, "DELETE")
                          }
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No manual bonuses" />
        )}
      </section>
    </div>
  );
}
