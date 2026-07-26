"use client";

import { FormEvent, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, errorMessage, json } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { CompetitionTemplate, Json, TemplateWrite } from "@/lib/types";
import { ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { Button } from "@/components/ui/Button";
import { CopyIcon, SaveIcon, TrashIcon } from "@/components/ui/icons";
import { Stack } from "@/components/ui/Card";
import { Checkbox, Input, Label, Select } from "@/components/ui/Field";
import { FieldHelp, LabelRow } from "@/components/ui/FieldHelp";
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
  | "pools"
  | "points"
  | "upsets"
  | "roster"
  | "phases"
  | "bonuses"
  | "tiebreaks"
  | "payouts"
  | "review";

const BASE_TABS: Array<{ id: Tab; label: string }> = [
  { id: "basics", label: "Basics" },
  { id: "pools", label: "Competitions" },
  { id: "points", label: "Points" },
  { id: "upsets", label: "Upsets" },
  { id: "roster", label: "Roster" },
  { id: "phases", label: "Phases" },
  { id: "bonuses", label: "Bonuses" },
  { id: "tiebreaks", label: "Tiebreaks" },
  { id: "payouts", label: "Payouts" },
  { id: "review", label: "Review" },
];

function tabsForBuyIn(buyIn: number | ""): Array<{ id: Tab; label: string }> {
  const hasBuyIn = buyIn !== "" && Number(buyIn) > 0;
  return BASE_TABS.filter((t) => t.id !== "payouts" || hasBuyIn);
}

type FormState = {
  label: string;
  draft_style: string;
  preassign_mode: string;
  buy_in: number | "";
  featured: boolean;
  made_by_staff: boolean;
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
  label: "",
  draft_style: "linear",
  preassign_mode: "none",
  buy_in: "",
  featured: false,
  made_by_staff: false,
  result_points: { win: 3, draw: 1, loss: 0 },
  upset_rules: {
    enabled: true,
    rank_source: "league_table_at_kickoff",
    ranking_list_key: null,
    min_played: 8,
    thresholds: [
      {
        key: "minor_upset",
        name: "Minor upset",
        result: "win",
        min_gap: 5,
        max_gap: 9,
        points: 1,
      },
      {
        key: "major_upset",
        name: "Major upset",
        result: "win",
        min_gap: 10,
        max_gap: null,
        points: 3,
      },
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
  payouts: [{ label: "Season 1st", phase: "season", position: 1, amount: 100 }],
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
  const buyIn = Number(item.buy_in);
  return {
    label: item.label,
    draft_style: item.draft_style,
    preassign_mode: item.preassign_mode,
    buy_in: Number.isFinite(buyIn) ? buyIn : "",
    featured: Boolean(item.featured),
    made_by_staff: Boolean(item.made_by_staff),
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

function toWrite(form: FormState, includeStaffFlags: boolean): TemplateWrite {
  const buyIn = form.buy_in === "" ? 0 : Number(form.buy_in);
  return {
    label: form.label,
    draft_style: form.draft_style,
    preassign_mode: form.preassign_mode,
    buy_in: buyIn,
    result_points: form.result_points as Record<string, Json>,
    upset_rules: serializeUpsetRules(form.upset_rules) as Record<string, Json>,
    leaderboard_phases: form.leaderboard_phases as unknown as Record<string, Json>[],
    leaderboard_tiebreaks: form.leaderboard_tiebreaks.map((t) => ({
      metric: t.metric,
      direction: t.direction,
      ...(t.event_types.length ? { event_types: t.event_types } : {}),
      ...(t.bonus_type_keys.length ? { bonus_type_keys: t.bonus_type_keys } : {}),
    })),
    payouts: (buyIn > 0 ? form.payouts : []) as unknown as Json[],
    pool_definitions: form.pool_definitions as unknown as Json[],
    bonus_types: form.bonus_types as unknown as Json[],
    roster_slots: form.roster_slots as unknown as Json[],
    ...(includeStaffFlags
      ? { featured: form.featured, made_by_staff: form.made_by_staff }
      : {}),
  };
}

function StepTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mb-3 flex items-start gap-2">
      <h3 className="text-base font-extrabold text-ink">{label}</h3>
      <FieldHelp label={label}>{children}</FieldHelp>
    </div>
  );
}

function ReviewBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-surface-2/40 px-3 py-2.5">
      <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-muted">{title}</h4>
      <div className="space-y-0.5 font-semibold text-ink">{children}</div>
    </div>
  );
}

export function TemplateEditor({
  templateId,
  onSaved,
}: {
  templateId?: string;
  onSaved?: (item: CompetitionTemplate) => void;
}) {
  const { isAdmin } = useAuth();
  const isNew = !templateId || templateId === "new";
  const [form, setForm] = useState<FormState>(structuredClone(blank));
  const [canEdit, setCanEdit] = useState(true);
  const [stepIndex, setStepIndex] = useState(0);
  const [highestStep, setHighestStep] = useState(0);
  const [stepError, setStepError] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!isNew);
  const readOnly = !isNew && !canEdit;

  const tabs = useMemo(() => tabsForBuyIn(form.buy_in), [form.buy_in]);
  const step = tabs[Math.min(stepIndex, tabs.length - 1)] ?? tabs[0];
  const isFirst = stepIndex === 0;
  const isLast = stepIndex >= tabs.length - 1;

  useEffect(() => {
    if (stepIndex >= tabs.length) {
      setStepIndex(Math.max(0, tabs.length - 1));
    }
  }, [tabs.length, stepIndex]);

  useEffect(() => {
    if (isNew) {
      setForm(structuredClone(blank));
      setCanEdit(true);
      setStepIndex(0);
      setHighestStep(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    api<CompetitionTemplate>(`/templates/${templateId}`)
      .then((item) => {
        setForm(fromTemplate(item));
        setCanEdit(Boolean(item.can_edit));
        setStepIndex(0);
        setHighestStep(0);
      })
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [templateId, isNew]);

  function goToStep(index: number) {
    if (index < 0 || index >= tabs.length) return;
    // Only allow jumping back to earlier steps
    if (index > stepIndex) return;
    setStepError("");
    setStepIndex(index);
  }

  function goNext() {
    if (step.id === "basics" && !form.label.trim()) {
      setStepError("Enter a template name to continue.");
      return;
    }
    setStepError("");
    if (!isLast) {
      setStepIndex((i) => {
        const next = Math.min(i + 1, tabs.length - 1);
        setHighestStep((h) => Math.max(h, next));
        return next;
      });
    }
  }

  function goBack() {
    setStepError("");
    setStepIndex((i) => Math.max(i - 1, 0));
  }

  async function save(e?: FormEvent) {
    e?.preventDefault();
    if (readOnly) return;
    if (!form.label.trim()) {
      setStepIndex(0);
      setStepError("Enter a template name to continue.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const item = await api<CompetitionTemplate>(
        isNew ? "/templates" : `/templates/${templateId}`,
        json(isNew ? "POST" : "PATCH", toWrite(form, isAdmin)),
      );
      setMessage("Template saved.");
      setCanEdit(Boolean(item.can_edit));
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
    setError("");
    setMessage("");
    try {
      const item = await api<CompetitionTemplate>(
        `/templates/${templateId}/duplicate`,
        json("POST"),
      );
      setMessage(`Copied as ${item.label}.`);
      onSaved?.(item);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!templateId || isNew || readOnly) return;
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
    <form
      className="flex flex-col gap-4 animate-in"
      onSubmit={(e) => {
        e.preventDefault();
        if (isLast && !readOnly) void save();
      }}
    >
      {error && <ErrorState error={error} />}
      {message && <StatusBanner tone="success">{message}</StatusBanner>}
      {readOnly && (
        <StatusBanner tone="info">
          You can use this template as-is, or copy it to make your own changes.
        </StatusBanner>
      )}

      <div className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-sm font-bold text-ink">{step.label}</p>
          <p className="text-xs font-semibold text-muted">
            Step {stepIndex + 1} of {tabs.length}
          </p>
        </div>
        <div className="flex gap-1 overflow-x-auto" aria-label="Template steps">
          {tabs.map((t, i) => {
            const reached = i <= highestStep;
            const active = i === stepIndex;
            const canJumpBack = i < stepIndex;
            return (
              <button
                key={t.id}
                type="button"
                disabled={!canJumpBack && !active}
                onClick={() => goToStep(i)}
                className={cn(
                  "h-1.5 min-w-6 flex-1 rounded-full transition",
                  active ? "bg-brand" : reached ? "bg-brand/35" : "bg-surface-2",
                  canJumpBack && "cursor-pointer hover:bg-brand/60",
                )}
                aria-label={`${t.label}${active ? " (current)" : ""}`}
                aria-current={active ? "step" : undefined}
              />
            );
          })}
        </div>
      </div>

      {stepError && <StatusBanner tone="error">{stepError}</StatusBanner>}

      <fieldset disabled={readOnly} className="min-w-0 border-0 p-0">
        <div role="group" aria-label={step.label}>
          {step.id === "basics" && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Label className="sm:col-span-2">
                Name
                <Input
                  required
                  value={form.label}
                  onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
                />
              </Label>
              <Label>
                <LabelRow>
                  Draft style
                  <FieldHelp label="Draft style">
                    <p className="mb-2">Controls pick order across draft rounds.</p>
                    <ul className="list-disc space-y-1 pl-4">
                      <li>
                        <strong className="text-ink">Linear</strong> — same order every round
                        (1→N).
                      </li>
                      <li>
                        <strong className="text-ink">Snake</strong> — order reverses each round
                        (1→N, then N→1).
                      </li>
                    </ul>
                  </FieldHelp>
                </LabelRow>
                <Select
                  value={form.draft_style}
                  onChange={(e) => setForm((f) => ({ ...f, draft_style: e.target.value }))}
                >
                  <option value="linear">Linear</option>
                  <option value="snake">Snake</option>
                </Select>
              </Label>
              <Label>
                <LabelRow>
                  Preassign mode
                  <FieldHelp label="Preassign mode">
                    <p className="mb-2">Whether clubs can be assigned before the live draft.</p>
                    <ul className="list-disc space-y-1 pl-4">
                      <li>
                        <strong className="text-ink">None</strong> — no pre-draft assignments.
                      </li>
                      <li>
                        <strong className="text-ink">Supported</strong> — commissioners can
                        preassign clubs; the draft continues for the rest.
                      </li>
                      <li>
                        <strong className="text-ink">Optional</strong> — preassign is available but
                        not required; each league chooses whether to use it.
                      </li>
                    </ul>
                  </FieldHelp>
                </LabelRow>
                <Select
                  value={form.preassign_mode}
                  onChange={(e) => setForm((f) => ({ ...f, preassign_mode: e.target.value }))}
                >
                  <option value="none">None</option>
                  <option value="supported">Supported</option>
                  <option value="optional">Optional</option>
                </Select>
              </Label>
              <Label className="max-w-xs">
                <LabelRow>
                  Buy-in
                  <FieldHelp label="Buy-in">
                    Entry amount seeded onto leagues from this template. Leave empty for none. When
                    set, a Payouts step appears later in the wizard.
                  </FieldHelp>
                </LabelRow>
                <Input
                  type="number"
                  min={0}
                  step="any"
                  placeholder="Optional"
                  value={form.buy_in}
                  onChange={(e) => {
                    const v = e.target.value;
                    setForm((f) => ({
                      ...f,
                      buy_in: v === "" ? "" : Number(v),
                    }));
                  }}
                />
              </Label>
              {isAdmin && (
                <div className="flex flex-col gap-3 sm:col-span-2">
                  <label className="flex min-h-11 items-center gap-3 text-sm font-semibold text-ink">
                    <Checkbox
                      checked={form.featured}
                      onChange={(e) => setForm((f) => ({ ...f, featured: e.target.checked }))}
                    />
                    <span className="inline-flex items-center gap-1.5">
                      Featured
                      <FieldHelp label="Featured">
                        Shows a Featured badge on the create-league hub so this template is easier
                        to discover.
                      </FieldHelp>
                    </span>
                  </label>
                  <label className="flex min-h-11 items-center gap-3 text-sm font-semibold text-ink">
                    <Checkbox
                      checked={form.made_by_staff}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, made_by_staff: e.target.checked }))
                      }
                    />
                    <span className="inline-flex items-center gap-1.5">
                      Made by staff
                      <FieldHelp label="Made by staff">
                        Marks this as an official Midtable template. Users can filter the hub by
                        this badge.
                      </FieldHelp>
                    </span>
                  </label>
                </div>
              )}
            </div>
          )}

          {step.id === "points" && (
            <>
              <StepTip label="Points">
                Points awarded for match results (win, draw, loss). These seed onto leagues created
                from this template.
              </StepTip>
              <ResultPointsEditor
                value={form.result_points}
                onChange={(result_points) => setForm((f) => ({ ...f, result_points }))}
              />
            </>
          )}
          {step.id === "upsets" && (
            <>
              <StepTip label="Upsets">
                <p className="mb-2">
                  Bonus points when a lower-ranked side gets a result against a higher-ranked one.
                </p>
                <p className="mb-1 font-semibold text-ink">Rank source</p>
                <ul className="list-disc space-y-1 pl-4">
                  <li>
                    <strong className="text-ink">League table at kickoff</strong> — uses the live
                    table standing at match time.
                  </li>
                  <li>
                    <strong className="text-ink">Fixed ranking list</strong> — uses a snapshot
                    ranking list for the event.
                  </li>
                </ul>
              </StepTip>
              <UpsetRulesEditor
                value={form.upset_rules}
                onChange={(upset_rules) => setForm((f) => ({ ...f, upset_rules }))}
                allowCustomLists={form.pool_definitions.length > 0}
              />
            </>
          )}
          {step.id === "pools" && (
            <>
              <StepTip label="Competitions">
                Real-world leagues or cups that feed the draft pool. Managers draft clubs from these
                competitions.
              </StepTip>
              <PoolDefinitionsEditor
                value={form.pool_definitions}
                onChange={(pool_definitions) => setForm((f) => ({ ...f, pool_definitions }))}
              />
            </>
          )}
          {step.id === "roster" && (
            <>
              <StepTip label="Roster">
                How many club slots each manager gets, and which competition those slots pull from.
              </StepTip>
              <RosterSlotsEditor
                value={form.roster_slots}
                onChange={(roster_slots) => setForm((f) => ({ ...f, roster_slots }))}
                poolOptions={form.pool_definitions.map((p) => ({
                  value: p.key,
                  label: p.label || p.key,
                }))}
              />
            </>
          )}
          {step.id === "phases" && (
            <>
              <StepTip label="Phases">
                <p className="mb-2">
                  Stages that can split standings and payouts (for example half-seasons).
                </p>
                <p className="mb-1 font-semibold text-ink">Match filter</p>
                <ul className="list-disc space-y-1 pl-4">
                  <li>
                    <strong className="text-ink">Matchweek range</strong> — include fixtures in a
                    week range.
                  </li>
                  <li>
                    <strong className="text-ink">Stages</strong> — include specific competition
                    stages.
                  </li>
                </ul>
              </StepTip>
              <PhasesEditor
                value={form.leaderboard_phases}
                onChange={(leaderboard_phases) => setForm((f) => ({ ...f, leaderboard_phases }))}
                bonusTypeOptions={form.bonus_types.map((b) => ({
                  value: b.key,
                  label: b.label || b.key,
                }))}
              />
            </>
          )}
          {step.id === "tiebreaks" && (
            <>
              <StepTip label="Tiebreaks">
                Order used when managers are level on points — for example total points, then upset
                points, then bonuses.
              </StepTip>
              <TiebreaksEditor
                value={form.leaderboard_tiebreaks}
                onChange={(leaderboard_tiebreaks) =>
                  setForm((f) => ({ ...f, leaderboard_tiebreaks }))
                }
                eventTypeOptions={eventOptionsFromUpsetKeys(
                  form.upset_rules.thresholds.map((t) => ({ key: t.key, name: t.name })),
                )}
                bonusTypeOptions={form.bonus_types.map((b) => ({
                  value: b.key,
                  label: b.label || b.key,
                }))}
              />
            </>
          )}
          {step.id === "bonuses" && (
            <>
              <StepTip label="Bonuses">
                Manual or season-end bonus categories (for example player of the season) that
                commissioners can award.
              </StepTip>
              <BonusTypesEditor
                value={form.bonus_types}
                onChange={(bonus_types) => setForm((f) => ({ ...f, bonus_types }))}
              />
            </>
          )}
          {step.id === "payouts" && (
            <div className="flex flex-col gap-4">
              <StepTip label="Payouts">
                Prize amounts by phase and finishing place. Buy-in was set on Basics (
                {form.buy_in === "" ? "0" : form.buy_in}).
              </StepTip>
              <PayoutsEditor
                value={form.payouts}
                onChange={(payouts) => setForm((f) => ({ ...f, payouts }))}
                phaseOptions={form.leaderboard_phases.map((p) => ({
                  value: p.key,
                  label: p.label || p.key,
                }))}
              />
            </div>
          )}
          {step.id === "review" && (
            <div className="flex flex-col gap-4 text-sm">
              <StepTip label="Review">
                Check the template before saving. Use Back or the step bar to edit a section.
              </StepTip>
              <ReviewBlock title="Basics">
                <div>{form.label || "—"}</div>
                <div>
                  Draft: {form.draft_style} · Preassign: {form.preassign_mode}
                </div>
                <div>
                  Buy-in: {form.buy_in === "" || Number(form.buy_in) === 0 ? "None" : form.buy_in}
                </div>
              </ReviewBlock>
              <ReviewBlock title="Competitions">
                {form.pool_definitions.length === 0 ? (
                  <div className="text-muted">None</div>
                ) : (
                  form.pool_definitions.map((p) => (
                    <div key={p.key}>
                      {p.label || p.key}
                      {p.competition_code ? ` · ${p.competition_code}` : ""}
                      {p.season_year ? ` · ${p.season_year}` : ""}
                    </div>
                  ))
                )}
              </ReviewBlock>
              <ReviewBlock title="Points">
                Win {form.result_points.win} · Draw {form.result_points.draw} · Loss{" "}
                {form.result_points.loss}
              </ReviewBlock>
              <ReviewBlock title="Upsets">
                {form.upset_rules.enabled ? "Enabled" : "Disabled"}
                {" · "}
                {form.upset_rules.rank_source === "fixed_ranking_at_event_start"
                  ? "Fixed ranking list"
                  : "League table at kickoff"}
                {form.upset_rules.rank_source === "fixed_ranking_at_event_start" &&
                  form.upset_rules.ranking_list_key && (
                    <> · list selected</>
                  )}
                <div className="text-muted">
                  {form.upset_rules.thresholds.length} threshold
                  {form.upset_rules.thresholds.length === 1 ? "" : "s"}
                </div>
              </ReviewBlock>
              <ReviewBlock title="Roster">
                {form.roster_slots.length === 0
                  ? "None"
                  : form.roster_slots
                      .map((s) => `${s.count}× ${s.label || s.pool_key}`)
                      .join(", ")}
              </ReviewBlock>
              <ReviewBlock title="Phases">
                {form.leaderboard_phases.length === 0
                  ? "None"
                  : form.leaderboard_phases.map((p) => p.label || p.key).join(", ")}
              </ReviewBlock>
              <ReviewBlock title="Bonuses">
                {form.bonus_types.length === 0
                  ? "None"
                  : form.bonus_types.map((b) => b.label || b.key).join(", ")}
              </ReviewBlock>
              <ReviewBlock title="Tiebreaks">
                {form.leaderboard_tiebreaks.length === 0
                  ? "None"
                  : form.leaderboard_tiebreaks.map((t) => t.metric).join(" → ")}
              </ReviewBlock>
              {form.buy_in !== "" && Number(form.buy_in) > 0 && (
                <ReviewBlock title="Payouts">
                  {form.payouts.length === 0
                    ? "None"
                    : form.payouts
                        .map((p) => `${p.label || `#${p.position}`}: ${p.amount}`)
                        .join(", ")}
                </ReviewBlock>
              )}
            </div>
          )}
        </div>
      </fieldset>

      <Stack gap="sm">
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="secondary" disabled={isFirst} onClick={goBack}>
            Back
          </Button>
          {!isLast && (
            <Button type="button" variant="primary" onClick={goNext}>
              Next
            </Button>
          )}
          {isLast && !readOnly && (
            <IconButton type="submit" label="Save template" variant="primary" busy={busy}>
              <SaveIcon />
            </IconButton>
          )}
          {!isNew && (
            <>
              <IconButton
                type="button"
                label="Copy template"
                variant={readOnly ? "primary" : "secondary"}
                busy={busy}
                onClick={duplicate}
              >
                <CopyIcon />
              </IconButton>
              {!readOnly && (
                <IconButton
                  type="button"
                  label="Delete template"
                  variant="danger"
                  busy={busy}
                  onClick={remove}
                >
                  <TrashIcon />
                </IconButton>
              )}
            </>
          )}
        </div>
      </Stack>
    </form>
  );
}
