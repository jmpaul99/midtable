"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { CompetitionTemplate, Json, TemplateWrite } from "@/lib/types";
import { ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { CopyIcon, SaveIcon, TrashIcon } from "@/components/ui/icons";
import { Stack } from "@/components/ui/Card";
import { Input, Label, Select } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import {
  BonusTypesEditor,
  eventOptionsFromUpsetKeys,
  normalizeBonusTypes,
  normalizePhases,
  normalizePayouts,
  normalizePoolDefinitions,
  normalizeResultPoints,
  normalizeRosterSlots,
  normalizeTiebreaks,
  normalizeUpsetRules,
  PhasesEditor,
  PayoutsEditor,
  PoolDefinitionsEditor,
  ResultPointsEditor,
  RosterSlotsEditor,
  serializeUpsetRules,
  TiebreaksEditor,
  UpsetRulesEditor,
  type BonusTypeDef,
  type LeaderboardPhase,
  type PayoutRow,
  type PoolDefinition,
  type ResultPoints,
  type RosterSlot,
  type TiebreakRung,
  type UpsetRules,
} from "@/components/settings";

type Tab =
  | "basics"
  | "points"
  | "upsets"
  | "pools"
  | "roster"
  | "phases"
  | "tiebreaks"
  | "bonuses"
  | "payouts";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "basics", label: "Basics" },
  { id: "points", label: "Points" },
  { id: "upsets", label: "Upsets" },
  { id: "pools", label: "Competitions" },
  { id: "roster", label: "Roster" },
  { id: "phases", label: "Phases" },
  { id: "tiebreaks", label: "Tiebreaks" },
  { id: "bonuses", label: "Bonuses" },
  { id: "payouts", label: "Payouts" },
];

type FormState = {
  key: string;
  label: string;
  draft_style: string;
  preassign_mode: string;
  buy_in: number;
  result_points: ResultPoints;
  upset_rules: UpsetRules;
  leaderboard_phases: LeaderboardPhase[];
  leaderboard_tiebreaks: TiebreakRung[];
  payouts: PayoutRow[];
  pool_definitions: PoolDefinition[];
  bonus_types: BonusTypeDef[];
  roster_slots: RosterSlot[];
};

const blank: FormState = {
  key: "",
  label: "",
  draft_style: "linear",
  preassign_mode: "none",
  buy_in: 50,
  result_points: { win: 3, draw: 1, loss: 0 },
  upset_rules: {
    enabled: true,
    rank_source: "league_table_at_kickoff",
    ranking_list_key: null,
    min_played: 8,
    thresholds: [
      { key: "minor_upset", result: "win", min_gap: 5, max_gap: 9, points: 1 },
      { key: "major_upset", result: "win", min_gap: 10, max_gap: null, points: 3 },
    ],
  },
  leaderboard_phases: [],
  leaderboard_tiebreaks: [
    { metric: "total_points", direction: "desc", event_types: [], bonus_type_keys: [] },
    {
      metric: "event_points",
      direction: "desc",
      event_types: ["minor_upset", "major_upset"],
      bonus_type_keys: [],
    },
  ],
  payouts: [
    { label: "Season 1st", phase: "season", position: 1, amount: 100 },
    { label: "Season 2nd", phase: "season", position: 2, amount: 50 },
  ],
  roster_slots: [],
  pool_definitions: [
    {
      key: "pl",
      label: "Premier League",
      scores_match_results: true,
      slot_count: 5,
      sort_order: 1,
      provider: "football-data.org",
      competition_code: "PL",
      season_year: 2026,
      tie_break_order: ["points", "gd", "gf", "name"],
    },
  ],
  bonus_types: [],
};

function fromTemplate(item: CompetitionTemplate): FormState {
  return {
    key: item.key,
    label: item.label,
    draft_style: item.draft_style,
    preassign_mode: item.preassign_mode,
    buy_in: Number(item.buy_in),
    result_points: normalizeResultPoints(item.result_points),
    upset_rules: normalizeUpsetRules(item.upset_rules),
    leaderboard_phases: normalizePhases(item.leaderboard_phases),
    leaderboard_tiebreaks: normalizeTiebreaks(item.leaderboard_tiebreaks),
    payouts: normalizePayouts(item.payouts),
    pool_definitions: normalizePoolDefinitions(item.pool_definitions),
    bonus_types: normalizeBonusTypes(item.bonus_types),
    roster_slots: normalizeRosterSlots(item.roster_slots),
  };
}

function toWrite(form: FormState): TemplateWrite {
  return {
    key: form.key,
    label: form.label,
    draft_style: form.draft_style,
    preassign_mode: form.preassign_mode,
    buy_in: form.buy_in,
    result_points: form.result_points as Record<string, Json>,
    upset_rules: serializeUpsetRules(form.upset_rules) as Record<string, Json>,
    leaderboard_phases: form.leaderboard_phases as unknown as Record<string, Json>[],
    leaderboard_tiebreaks: form.leaderboard_tiebreaks.map((t) => ({
      metric: t.metric,
      direction: t.direction,
      ...(t.event_types.length ? { event_types: t.event_types } : {}),
      ...(t.bonus_type_keys.length ? { bonus_type_keys: t.bonus_type_keys } : {}),
    })),
    payouts: form.payouts as unknown as Json[],
    pool_definitions: form.pool_definitions as unknown as Json[],
    bonus_types: form.bonus_types as unknown as Json[],
    roster_slots: form.roster_slots as unknown as Json[],
  };
}

export function TemplateEditor({
  templateId,
  onSaved,
}: {
  templateId?: string;
  onSaved?: (item: CompetitionTemplate) => void;
}) {
  const isNew = !templateId || templateId === "new";
  const [form, setForm] = useState<FormState>(structuredClone(blank));
  const [tab, setTab] = useState<Tab>("basics");
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
    api<CompetitionTemplate>(`/templates/${templateId}`)
      .then((item) => setForm(fromTemplate(item)))
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [templateId, isNew]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const item = await api<CompetitionTemplate>(
        isNew ? "/templates" : `/templates/${templateId}`,
        json(isNew ? "POST" : "PATCH", toWrite(form)),
      );
      setMessage("Template saved.");
      onSaved?.(item);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function duplicate() {
    if (!templateId || isNew) return;
    setBusy(true);
    try {
      const item = await api<CompetitionTemplate>(
        `/templates/${templateId}/duplicate`,
        json("POST"),
      );
      setMessage(`Duplicated as ${item.key}`);
      onSaved?.(item);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!templateId || isNew) return;
    if (!confirm("Delete this template?")) return;
    setBusy(true);
    try {
      await api(`/templates/${templateId}`, json("DELETE"));
      setMessage("Deleted.");
      onSaved?.({ id: "" } as CompetitionTemplate);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading label="Loading template" />;

  return (
    <form className="flex flex-col gap-4 animate-in" onSubmit={save}>
      {error && <ErrorState error={error} />}
      {message && <StatusBanner tone="success">{message}</StatusBanner>}

      <div
        className="flex gap-1 overflow-x-auto rounded-xl bg-surface-2 p-1"
        role="tablist"
        aria-label="Template sections"
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

      <div role="tabpanel">
        {tab === "basics" && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Label>
              Key
              <Input
                required
                value={form.key}
                disabled={!isNew}
                onChange={(e) => setForm((f) => ({ ...f, key: e.target.value }))}
              />
            </Label>
            <Label>
              Label
              <Input
                required
                value={form.label}
                onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              />
            </Label>
            <Label>
              Draft style
              <Select
                value={form.draft_style}
                onChange={(e) => setForm((f) => ({ ...f, draft_style: e.target.value }))}
              >
                <option value="linear">Linear</option>
                <option value="snake">Snake</option>
              </Select>
            </Label>
            <Label>
              Preassign mode
              <Select
                value={form.preassign_mode}
                onChange={(e) => setForm((f) => ({ ...f, preassign_mode: e.target.value }))}
              >
                <option value="none">None</option>
                <option value="supported">Supported</option>
                <option value="optional">Optional</option>
              </Select>
            </Label>
            <Label>
              Buy-in
              <Input
                type="number"
                value={form.buy_in}
                onChange={(e) => setForm((f) => ({ ...f, buy_in: Number(e.target.value) }))}
              />
            </Label>
          </div>
        )}

        {tab === "points" && (
          <ResultPointsEditor
            value={form.result_points}
            onChange={(result_points) => setForm((f) => ({ ...f, result_points }))}
          />
        )}
        {tab === "upsets" && (
          <UpsetRulesEditor
            value={form.upset_rules}
            onChange={(upset_rules) => setForm((f) => ({ ...f, upset_rules }))}
          />
        )}
        {tab === "pools" && (
          <PoolDefinitionsEditor
            value={form.pool_definitions}
            onChange={(pool_definitions) => setForm((f) => ({ ...f, pool_definitions }))}
          />
        )}
        {tab === "roster" && (
          <RosterSlotsEditor
            value={form.roster_slots}
            onChange={(roster_slots) => setForm((f) => ({ ...f, roster_slots }))}
          />
        )}
        {tab === "phases" && (
          <PhasesEditor
            value={form.leaderboard_phases}
            onChange={(leaderboard_phases) => setForm((f) => ({ ...f, leaderboard_phases }))}
            bonusTypeOptions={form.bonus_types.map((b) => ({
              value: b.key,
              label: b.label || b.key,
            }))}
          />
        )}
        {tab === "tiebreaks" && (
          <TiebreaksEditor
            value={form.leaderboard_tiebreaks}
            onChange={(leaderboard_tiebreaks) => setForm((f) => ({ ...f, leaderboard_tiebreaks }))}
            eventTypeOptions={eventOptionsFromUpsetKeys(
              form.upset_rules.thresholds.map((t) => t.key),
            )}
            bonusTypeOptions={form.bonus_types.map((b) => ({
              value: b.key,
              label: b.label || b.key,
            }))}
          />
        )}
        {tab === "bonuses" && (
          <BonusTypesEditor
            value={form.bonus_types}
            onChange={(bonus_types) => setForm((f) => ({ ...f, bonus_types }))}
          />
        )}
        {tab === "payouts" && (
          <PayoutsEditor
            value={form.payouts}
            onChange={(payouts) => setForm((f) => ({ ...f, payouts }))}
          />
        )}
      </div>

      <Stack gap="sm">
        <div className="flex flex-wrap gap-2">
          <IconButton type="submit" label="Save template" variant="primary" busy={busy}>
            <SaveIcon />
          </IconButton>
          {!isNew && (
            <>
              <IconButton
                type="button"
                label="Duplicate template"
                variant="secondary"
                busy={busy}
                onClick={duplicate}
              >
                <CopyIcon />
              </IconButton>
              <IconButton
                type="button"
                label="Delete template"
                variant="danger"
                busy={busy}
                onClick={remove}
              >
                <TrashIcon />
              </IconButton>
            </>
          )}
        </div>
      </Stack>
    </form>
  );
}
