"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type {
  CompetitionTemplate,
  Json,
  LeaderboardRung,
  PoolConfig,
  TemplateWrite,
} from "@/lib/types";
import { ErrorState, JsonEditor, Status } from "./State";

const blank: TemplateWrite = {
  code: "",
  name: "",
  provider: "football-data.org",
  provider_competition_code: "",
  default_team_count: 20,
  default_roster_size: 1,
  pools: [
    {
      key: "main",
      name: "Main pool",
      provider_competition_code: "",
      slots_per_member: 1,
      slot_label: "Club",
      scoring_enabled: true,
    },
  ],
  scoring: {
    result_points: { win: 3, draw: 1, loss: 0 },
    table_tiebreaks: ["points", "goal_difference", "goals_for", "name"],
    upset: {
      minimum_matches_played: 8,
      thresholds: [
        {
          key: "upset",
          result: "win",
          minimum_position_gap: 5,
          maximum_position_gap: null,
          bonus: 1,
        },
      ],
    },
  },
  phases: [],
  leaderboard_tiebreaks: [
    { metric: "total_points", direction: "desc" },
    { metric: "event_points", event_types: ["upset"], direction: "desc" },
    { metric: "event_count", event_types: ["win"], direction: "desc" },
  ],
  bonuses: {},
  payouts: [
    { rank: 1, amount: 100 },
    { rank: 2, amount: 60 },
    { rank: 3, amount: 30 },
  ],
  draft: { format: "linear" },
  is_active: true,
};

function strip(item: CompetitionTemplate): TemplateWrite {
  const { id: _id, created_at: _c, updated_at: _u, ...rest } = item;
  return structuredClone(rest);
}

export function TemplateEditor({
  templateId,
  onSaved,
}: {
  templateId?: string;
  onSaved?: (item: CompetitionTemplate) => void;
}) {
  const isNew = !templateId || templateId === "new";
  const [form, setForm] = useState<TemplateWrite>(structuredClone(blank));
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!isNew);

  useEffect(() => {
    if (isNew) {
      setForm(structuredClone(blank));
      setLoading(false);
      return;
    }
    setLoading(true);
    api<CompetitionTemplate>(`/competition-templates/${templateId}`)
      .then((item) => setForm(strip(item)))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [templateId, isNew]);

  function set<K extends keyof TemplateWrite>(key: K, value: TemplateWrite[K]) {
    setForm((v) => ({ ...v, [key]: value }));
  }

  function pool(index: number, patch: Partial<PoolConfig>) {
    set(
      "pools",
      form.pools.map((p, i) => (i === index ? { ...p, ...patch } : p)),
    );
  }

  function rung(index: number, patch: Partial<LeaderboardRung>) {
    set(
      "leaderboard_tiebreaks",
      form.leaderboard_tiebreaks.map((value, i) => (i === index ? { ...value, ...patch } : value)),
    );
  }

  function moveRung(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= form.leaderboard_tiebreaks.length) return;
    const next = [...form.leaderboard_tiebreaks];
    [next[index], next[target]] = [next[target], next[index]];
    set("leaderboard_tiebreaks", next);
  }

  const resultPoints =
    form.scoring.result_points &&
    typeof form.scoring.result_points === "object" &&
    !Array.isArray(form.scoring.result_points)
      ? (form.scoring.result_points as Record<string, Json>)
      : {};
  const upset =
    form.scoring.upset &&
    typeof form.scoring.upset === "object" &&
    !Array.isArray(form.scoring.upset)
      ? (form.scoring.upset as Record<string, Json>)
      : {};
  const thresholds = Array.isArray(upset.thresholds) ? upset.thresholds : [];
  const eventKeys = Array.from(
    new Set([
      ...Object.keys(resultPoints),
      ...thresholds.map((value) =>
        value && typeof value === "object" && !Array.isArray(value) && typeof value.key === "string"
          ? value.key
          : "upset",
      ),
    ]),
  );
  const bonusKeys = Object.keys(form.bonuses);

  function changeMetric(index: number, metric: LeaderboardRung["metric"]) {
    const next: LeaderboardRung = {
      metric,
      direction: form.leaderboard_tiebreaks[index].direction,
    };
    if (metric === "event_points" || metric === "event_count") {
      next.event_types = eventKeys.slice(0, 1);
    }
    if (metric === "bonus_points" || metric === "bonus_count") {
      next.bonus_type_keys = bonusKeys.slice(0, 1);
    }
    set(
      "leaderboard_tiebreaks",
      form.leaderboard_tiebreaks.map((value, i) => (i === index ? next : value)),
    );
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const total = form.pools.reduce((n, p) => n + p.slots_per_member, 0);
      const body = { ...form, default_roster_size: total };
      const item = await api<CompetitionTemplate>(
        isNew ? "/competition-templates" : `/competition-templates/${templateId}`,
        json(isNew ? "POST" : "PUT", body),
      );
      setMessage("Template saved.");
      setForm(strip(item));
      onSaved?.(item);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function duplicate() {
    if (isNew) return;
    const code = prompt("New template code (A-Z, 0-9, _ or -):");
    const name = prompt("New template name:");
    if (!code || !name) return;
    try {
      const item = await api<CompetitionTemplate>(
        `/competition-templates/${templateId}/duplicate`,
        json("POST", { code, name }),
      );
      setMessage("Template duplicated.");
      onSaved?.(item);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function deactivate() {
    if (isNew) return;
    try {
      await api(`/competition-templates/${templateId}`, json("DELETE"));
      setMessage("Template deactivated.");
      set("is_active", false);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (loading) {
    return (
      <div className="loading" role="status">
        <div className="stack" style={{ justifyItems: "center" }}>
          <i className="spinner" />
          <span>Loading template…</span>
        </div>
      </div>
    );
  }

  return (
    <form className="panel stack" onSubmit={save}>
      <div className="row between">
        <h2>{isNew ? "Create template" : "Edit template"}</h2>
        {!isNew && (
          <div className="row">
            <Status value={form.is_active ? "active" : "inactive"} />
            <button type="button" className="secondary" onClick={duplicate}>
              Duplicate
            </button>
            <button type="button" className="danger" onClick={deactivate}>
              Deactivate
            </button>
          </div>
        )}
      </div>
      {error && <ErrorState error={error} />}
      {message && <div className="notice">{message}</div>}

      <div className="form-grid">
        <label>
          Name
          <input required value={form.name} onChange={(e) => set("name", e.target.value)} />
        </label>
        <label>
          Code
          <input
            required
            pattern="[A-Z0-9_-]+"
            value={form.code}
            onChange={(e) => set("code", e.target.value.toUpperCase())}
          />
        </label>
        <label>
          Provider
          <input
            required
            value={form.provider}
            onChange={(e) => set("provider", e.target.value)}
          />
        </label>
        <label>
          Competition code
          <input
            required
            value={form.provider_competition_code}
            onChange={(e) => set("provider_competition_code", e.target.value)}
          />
        </label>
        <label>
          Default team count
          <input
            type="number"
            min={2}
            value={form.default_team_count}
            onChange={(e) => set("default_team_count", Number(e.target.value))}
          />
        </label>
        <label className="row">
          <input
            style={{ width: "auto" }}
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => set("is_active", e.target.checked)}
          />
          Active
        </label>
      </div>

      <section className="stack">
        <div className="row between">
          <h3>Pool definitions</h3>
          <button
            type="button"
            className="secondary"
            onClick={() =>
              set("pools", [
                ...form.pools,
                {
                  key: `pool_${form.pools.length + 1}`,
                  name: "New pool",
                  provider_competition_code: form.provider_competition_code,
                  slots_per_member: 1,
                  slot_label: "Club",
                  scoring_enabled: true,
                },
              ])
            }
          >
            Add pool
          </button>
        </div>
        {form.pools.map((p, i) => (
          <div className="panel inset form-grid" key={i}>
            <label>
              Key
              <input
                required
                pattern="[a-z0-9_]+"
                value={p.key}
                onChange={(e) => pool(i, { key: e.target.value })}
              />
            </label>
            <label>
              Name
              <input
                required
                value={p.name}
                onChange={(e) => pool(i, { name: e.target.value })}
              />
            </label>
            <label>
              Provider code
              <input
                required
                value={p.provider_competition_code}
                onChange={(e) => pool(i, { provider_competition_code: e.target.value })}
              />
            </label>
            <label>
              Slots / member
              <input
                type="number"
                min={1}
                value={p.slots_per_member}
                onChange={(e) => pool(i, { slots_per_member: Number(e.target.value) })}
              />
            </label>
            <label>
              Slot label
              <input
                required
                value={p.slot_label}
                onChange={(e) => pool(i, { slot_label: e.target.value })}
              />
            </label>
            <label className="row">
              <input
                style={{ width: "auto" }}
                type="checkbox"
                checked={p.scoring_enabled}
                onChange={(e) => pool(i, { scoring_enabled: e.target.checked })}
              />
              Scoring enabled
            </label>
            {form.pools.length > 1 && (
              <button
                type="button"
                className="danger full"
                onClick={() => set("pools", form.pools.filter((_, n) => n !== i))}
              >
                Remove pool
              </button>
            )}
          </div>
        ))}
        <div className="notice">
          Roster size is derived from pool slots:{" "}
          <strong>{form.pools.reduce((n, p) => n + p.slots_per_member, 0)}</strong>
        </div>
      </section>

      <div className="grid grid-2">
        <JsonEditor
          label="Result points, table tiebreak & upset rules"
          value={form.scoring}
          onChange={(v) => set("scoring", v as Record<string, Json>)}
        />
        <JsonEditor
          label="Phases"
          value={form.phases}
          onChange={(v) => set("phases", v as Record<string, Json>[])}
        />
        <JsonEditor
          label="Bonus catalog (type → points)"
          value={form.bonuses}
          onChange={(v) => set("bonuses", v as Record<string, number>)}
        />
        <JsonEditor
          label="Buy-in / payouts"
          value={form.payouts}
          onChange={(v) => set("payouts", v as Record<string, Json>[])}
        />
      </div>

      <section className="stack">
        <div className="row between">
          <h3>Leaderboard tiebreak rungs</h3>
          <button
            type="button"
            className="secondary"
            onClick={() =>
              set("leaderboard_tiebreaks", [
                ...form.leaderboard_tiebreaks,
                { metric: "total_points", direction: "desc" },
              ])
            }
          >
            Add rung
          </button>
        </div>
        {form.leaderboard_tiebreaks.map((value, index) => (
          <div className="panel inset form-grid" key={index}>
            <label>
              Metric
              <select
                value={value.metric}
                onChange={(e) => changeMetric(index, e.target.value as LeaderboardRung["metric"])}
              >
                <option value="total_points">Total points</option>
                <option value="event_points">Event points</option>
                <option value="event_count">Event count</option>
                <option value="bonus_points">Bonus points</option>
                <option value="bonus_count">Bonus count</option>
              </select>
            </label>
            <label>
              Direction
              <select
                value={value.direction}
                onChange={(e) =>
                  rung(index, { direction: e.target.value as "asc" | "desc" })
                }
              >
                <option value="desc">Highest first</option>
                <option value="asc">Lowest first</option>
              </select>
            </label>
            {(value.metric === "event_points" || value.metric === "event_count") && (
              <label className="full">
                Scoring event keys
                <select
                  multiple
                  required
                  size={Math.min(6, Math.max(2, eventKeys.length))}
                  value={value.event_types || []}
                  onChange={(e) =>
                    rung(index, {
                      event_types: Array.from(e.target.selectedOptions, (o) => o.value),
                    })
                  }
                >
                  {eventKeys.map((key) => (
                    <option value={key} key={key}>
                      {key}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {(value.metric === "bonus_points" || value.metric === "bonus_count") && (
              <label className="full">
                Manual bonus keys
                <select
                  multiple
                  required
                  size={Math.min(6, Math.max(2, bonusKeys.length))}
                  value={value.bonus_type_keys || []}
                  onChange={(e) =>
                    rung(index, {
                      bonus_type_keys: Array.from(e.target.selectedOptions, (o) => o.value),
                    })
                  }
                >
                  {bonusKeys.map((key) => (
                    <option value={key} key={key}>
                      {key}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="row full">
              <button
                type="button"
                className="secondary"
                disabled={index === 0}
                onClick={() => moveRung(index, -1)}
              >
                Move up
              </button>
              <button
                type="button"
                className="secondary"
                disabled={index === form.leaderboard_tiebreaks.length - 1}
                onClick={() => moveRung(index, 1)}
              >
                Move down
              </button>
              <button
                type="button"
                className="danger"
                disabled={form.leaderboard_tiebreaks.length === 1}
                onClick={() =>
                  set(
                    "leaderboard_tiebreaks",
                    form.leaderboard_tiebreaks.filter((_, i) => i !== index),
                  )
                }
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </section>

      <label>
        Draft format
        <select
          value={String(form.draft.format || "linear")}
          onChange={(e) => set("draft", { ...form.draft, format: e.target.value })}
        >
          <option value="linear">Linear</option>
          <option value="snake">Snake</option>
        </select>
      </label>

      <button type="submit" disabled={busy}>
        {busy ? "Saving…" : "Save template"}
      </button>
    </form>
  );
}
