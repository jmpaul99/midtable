"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState, type ReactNode } from "react";
import { api, errorMessage, json } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { CompetitionTemplate, Json, TemplateWrite } from "@/lib/types";
import { ErrorState, Loading, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { CopyIcon, PencilIcon, PlayIcon, SaveIcon, TrashIcon, XIcon } from "@/components/ui/icons";
import { Stack } from "@/components/ui/Card";
import { Checkbox, Input, Label } from "@/components/ui/Field";
import { FieldHelp, LabelRow } from "@/components/ui/FieldHelp";
import { ChoiceToggle } from "@/components/ui/ChoiceToggle";
import { useToast } from "@/components/ui/ToastProvider";
import { cn } from "@/lib/cn";
import {
  normalizeRosterClubOrder,
  type RosterClubOrder,
} from "@/lib/rosterClubOrder";
import {
  BonusTypesListEditor,
  eventOptionsFromUpsetKeys,
  LeaguePoolsEditor,
  normalizeBonusTypes,
  normalizePhases,
  normalizePayouts,
  normalizePoolDefinitions,
  normalizeResultPoints,
  serializeResultPoints,
  normalizeTiebreaks,
  normalizeUpsetRules,
  PhasesEditor,
  PayoutsEditor,
  ResultPointsEditor,
  serializeUpsetRules,
  TiebreaksEditor,
  UpsetRulesEditor,
  type BonusTypeDef,
  type LeaderboardPhase,
  type LeaguePoolEdit,
  type PayoutRow,
  type PoolDefinition,
  type ResultPoints,
  type TiebreakRung,
  type UpsetRules,
} from "@/components/settings";

const DEFAULT_TIE_BREAK_ORDER = ["points", "gd", "gf", "name"];

function poolsToEdit(defs: PoolDefinition[]): LeaguePoolEdit[] {
  return defs.map((p, i) => ({
    id: p.key ? `key:${p.key}` : `order:${p.sort_order || i + 1}`,
    key: p.key,
    label: p.label,
    sort_order: p.sort_order,
    slot_count: p.slot_count,
    scores_match_results: p.scores_match_results,
    competition_code: p.competition_code,
    season_year: p.season_year,
    provider: p.provider,
  }));
}

function poolsFromEdit(rows: LeaguePoolEdit[], prev: PoolDefinition[]): PoolDefinition[] {
  const prevByKey = new Map(prev.map((p) => [p.key, p]));
  const prevByCode = new Map(
    prev
      .filter((p) => p.competition_code)
      .map((p) => [p.competition_code.trim().toUpperCase(), p]),
  );
  return rows.map((r, i) => {
    const prevRow =
      (r.key && prevByKey.get(r.key)) ||
      (r.competition_code
        ? prevByCode.get(r.competition_code.trim().toUpperCase())
        : undefined);
    return {
      key: r.key,
      label: r.label,
      scores_match_results: r.scores_match_results,
      slot_count: r.slot_count,
      sort_order: r.sort_order || i + 1,
      provider: r.provider || "football-data.org",
      competition_code: r.competition_code,
      season_year: r.season_year,
      tie_break_order: prevRow?.tie_break_order?.length
        ? prevRow.tie_break_order
        : DEFAULT_TIE_BREAK_ORDER,
    };
  });
}

type Tab =
  | "basics"
  | "pools"
  | "points"
  | "upsets"
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
  { id: "phases", label: "Phases" },
  { id: "bonuses", label: "Bonuses" },
  { id: "tiebreaks", label: "Tiebreaks" },
  { id: "payouts", label: "Payouts" },
  { id: "review", label: "Review" },
];

type FormState = {
  label: string;
  max_members: number | "";
  draft_style: string;
  preassign_mode: string;
  preassign_count: number;
  buy_in: number | "";
  featured: boolean;
  made_by_staff: boolean;
  roster_club_order: RosterClubOrder;
  result_points: ResultPoints;
  upset_rules: UpsetRules;
  leaderboard_phases: LeaderboardPhase[];
  leaderboard_tiebreaks: TiebreakRung[];
  payouts: PayoutRow[];
  pool_definitions: PoolDefinition[];
  bonus_types: BonusTypeDef[];
};

const blank: FormState = {
  label: "",
  max_members: "",
  draft_style: "linear",
  preassign_mode: "off",
  preassign_count: 1,
  buy_in: "",
  featured: false,
  made_by_staff: false,
  roster_club_order: "draft",
  result_points: {
    win: 3,
    draw: 1,
    loss: 0,
    win_et: null,
    loss_et: null,
    win_pk: null,
    loss_pk: null,
    by_stage: {},
  },
  upset_rules: {
    enabled: false,
    rank_source: "league_table_at_kickoff",
    ranking_list_key: null,
    min_played: 0,
    thresholds: [],
  },
  leaderboard_phases: [],
  leaderboard_tiebreaks: [
    { metric: "total_points", direction: "desc", event_types: [], bonus_type_keys: [] },
  ],
  payouts: [],
  pool_definitions: [],
  bonus_types: [],
};

function fromTemplate(item: CompetitionTemplate): FormState {
  const buyIn = Number(item.buy_in);
  const maxMembers = Number(item.max_members);
  return {
    label: item.label,
    max_members: Number.isFinite(maxMembers) && maxMembers >= 2 ? maxMembers : "",
    draft_style: item.draft_style,
    preassign_mode:
      item.preassign_mode === "supported"
        ? "required"
        : item.preassign_mode === "none"
          ? "off"
          : item.preassign_mode || "off",
    preassign_count:
      typeof item.preassign_count === "number" && item.preassign_count >= 0
        ? Math.floor(item.preassign_count)
        : 1,
    buy_in: Number.isFinite(buyIn) ? buyIn : "",
    featured: Boolean(item.featured),
    made_by_staff: Boolean(item.made_by_staff),
    roster_club_order: normalizeRosterClubOrder(item.roster_club_order),
    result_points: normalizeResultPoints(item.result_points),
    upset_rules: normalizeUpsetRules(item.upset_rules),
    leaderboard_phases: normalizePhases(item.leaderboard_phases),
    leaderboard_tiebreaks: normalizeTiebreaks(item.leaderboard_tiebreaks),
    payouts: normalizePayouts(item.payouts),
    pool_definitions: normalizePoolDefinitions(item.pool_definitions),
    bonus_types: normalizeBonusTypes(item.bonus_types),
  };
}

function toWrite(form: FormState, includeStaffFlags: boolean): TemplateWrite {
  const buyIn = form.buy_in === "" ? 0 : Number(form.buy_in);
  const maxMembers = form.max_members === "" ? null : Number(form.max_members);
  return {
    label: form.label,
    max_members: maxMembers != null && Number.isFinite(maxMembers) ? maxMembers : null,
    draft_style: form.draft_style,
    preassign_mode: form.preassign_mode,
    preassign_count: form.preassign_count,
    buy_in: buyIn,
    result_points: serializeResultPoints(form.result_points) as Record<string, Json>,
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
    roster_slots: form.pool_definitions.map((p) => ({
      pool_key: p.key,
      count: p.slot_count,
      label: p.label || p.key,
    })) as unknown as Json[],
    roster_club_order: form.roster_club_order,
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

function humanizeKey(key: string): string {
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function formatPhaseFilter(filter: LeaderboardPhase["match_filter"]): string {
  if (filter.type === "matchweek_range") {
    return `Matchweeks ${filter.from}–${filter.to}`;
  }
  if (filter.type === "stage_in") {
    return filter.stages.length
      ? `Stages: ${filter.stages.map(humanizeKey).join(", ")}`
      : "Stages: none";
  }
  return "—";
}

function formatTiebreak(r: TiebreakRung): string {
  const dir = r.direction === "asc" ? "low → high" : "high → low";
  let label = humanizeKey(r.metric);
  if (r.event_types.length) {
    label += ` (${r.event_types.map(humanizeKey).join(", ")})`;
  }
  if (r.bonus_type_keys.length) {
    label += ` (${r.bonus_type_keys.map(humanizeKey).join(", ")})`;
  }
  return `${label} · ${dir}`;
}

function pointLine(
  label: string,
  value: number | null | undefined,
  inherit?: string,
): ReactNode | null {
  if (value == null) {
    return inherit ? (
      <div key={label} className="text-muted">
        {label}: inherit ({inherit})
      </div>
    ) : null;
  }
  return (
    <div key={label}>
      {label}: {value}
    </div>
  );
}

function TemplateSettingsSummary({ form }: { form: FormState }) {
  const stages = Object.entries(form.result_points.by_stage || {});
  const hasEtPk =
    form.result_points.win_et != null ||
    form.result_points.loss_et != null ||
    form.result_points.win_pk != null ||
    form.result_points.loss_pk != null;

  return (
    <div className="flex flex-col gap-3 text-sm">
      <ReviewBlock title="Basics">
        <div className="text-base">{form.label || "—"}</div>
        <div>Managers: {form.max_members === "" ? "—" : form.max_members}</div>
        <div>
          Draft: {form.draft_style === "snake" ? "Snake" : "Linear"}
          {" · "}
          Preassign:{" "}
          {form.preassign_mode === "off" || form.preassign_mode === "none"
            ? "Off"
            : form.preassign_mode === "required" || form.preassign_mode === "supported"
              ? `Required (${form.preassign_count})`
              : form.preassign_mode === "optional"
                ? `Optional (max ${form.preassign_count})`
                : humanizeKey(form.preassign_mode)}
        </div>
        {(form.featured || form.made_by_staff) && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {form.featured && (
              <span className="rounded-md bg-brand/10 px-2 py-0.5 text-xs font-bold text-brand">
                Featured
              </span>
            )}
            {form.made_by_staff && (
              <span className="rounded-md bg-surface-2 px-2 py-0.5 text-xs font-bold text-muted">
                Made by staff
              </span>
            )}
          </div>
        )}
      </ReviewBlock>

      <ReviewBlock title="Competitions">
        {form.pool_definitions.length > 1 && (
          <div className="mb-1">
            Roster after draft:{" "}
            {form.roster_club_order === "competition" ? "Competition order" : "Draft order"}
          </div>
        )}
        {form.pool_definitions.length === 0 ? (
          <div className="text-muted">None</div>
        ) : (
          <ul className="space-y-2">
            {form.pool_definitions.map((p) => (
              <li key={p.key} className="border-t border-line/60 pt-2 first:border-0 first:pt-0">
                <div>{p.label || p.key}</div>
                <div className="text-muted">
                  {[
                    p.competition_code || null,
                    p.season_year ? String(p.season_year) : null,
                    `${p.slot_count} slot${p.slot_count === 1 ? "" : "s"}`,
                    p.scores_match_results ? "scores results" : "no result scoring",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              </li>
            ))}
          </ul>
        )}
      </ReviewBlock>

      <ReviewBlock title="Points">
        <div>
          Win {form.result_points.win} · Draw {form.result_points.draw} · Loss{" "}
          {form.result_points.loss}
        </div>
        {hasEtPk && (
          <div className="mt-1 space-y-0.5 text-muted">
            {pointLine("Win (ET)", form.result_points.win_et, String(form.result_points.win))}
            {pointLine("Loss (ET)", form.result_points.loss_et, String(form.result_points.loss))}
            {pointLine("Win (PK)", form.result_points.win_pk, String(form.result_points.win))}
            {pointLine("Loss (PK)", form.result_points.loss_pk, String(form.result_points.loss))}
          </div>
        )}
        {stages.length > 0 && (
          <div className="mt-2 space-y-2">
            <div className="text-xs font-bold uppercase tracking-wide text-muted">
              Stage overrides ({stages.length})
            </div>
            {stages.map(([stage, pts]) => (
              <div key={stage} className="border-t border-line/60 pt-2">
                <div>{humanizeKey(stage)}</div>
                <div className="text-muted">
                  {[
                    pts.win != null ? `W ${pts.win}` : null,
                    pts.draw != null ? `D ${pts.draw}` : null,
                    pts.loss != null ? `L ${pts.loss}` : null,
                    pts.win_et != null ? `W ET ${pts.win_et}` : null,
                    pts.loss_et != null ? `L ET ${pts.loss_et}` : null,
                    pts.win_pk != null ? `W PK ${pts.win_pk}` : null,
                    pts.loss_pk != null ? `L PK ${pts.loss_pk}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "All inherit"}
                </div>
              </div>
            ))}
          </div>
        )}
      </ReviewBlock>

      <ReviewBlock title="Upsets">
        {form.upset_rules.enabled ? (
          <>
            <div>
              Enabled ·{" "}
              {form.upset_rules.rank_source === "fixed_ranking_at_event_start"
                ? "Fixed ranking list"
                : "League table at kickoff"}
              {form.upset_rules.rank_source === "fixed_ranking_at_event_start" &&
                form.upset_rules.ranking_list_key && (
                  <> · {humanizeKey(form.upset_rules.ranking_list_key)}</>
                )}
            </div>
            {form.upset_rules.min_played > 0 && (
              <div className="text-muted">
                Min games played for ranking: {form.upset_rules.min_played}
              </div>
            )}
            {form.upset_rules.thresholds.length === 0 ? (
              <div className="text-muted">No thresholds</div>
            ) : (
              <ul className="mt-1 space-y-1.5">
                {form.upset_rules.thresholds.map((t) => (
                  <li key={t.key} className="border-t border-line/60 pt-1.5 first:border-0 first:pt-0">
                    <div>{t.name || humanizeKey(t.key)}</div>
                    <div className="text-muted">
                      {humanizeKey(t.result)}
                      {" · gap "}
                      {t.max_gap == null ? `${t.min_gap}+` : `${t.min_gap}–${t.max_gap}`}
                      {" · "}
                      {t.points} pts
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <div className="text-muted">Disabled</div>
        )}
      </ReviewBlock>

      <ReviewBlock title="Phases">
        {form.leaderboard_phases.length === 0 ? (
          <div className="text-muted">None</div>
        ) : (
          <ul className="space-y-2">
            {form.leaderboard_phases.map((p) => (
              <li key={p.key} className="border-t border-line/60 pt-2 first:border-0 first:pt-0">
                <div>{p.label || p.key}</div>
                <div className="text-muted">{formatPhaseFilter(p.match_filter)}</div>
                {p.include_bonus_types.length > 0 && (
                  <div className="text-muted">
                    Bonuses: {p.include_bonus_types.map(humanizeKey).join(", ")}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </ReviewBlock>

      <ReviewBlock title="Bonuses">
        {form.bonus_types.length === 0 ? (
          <div className="text-muted">None</div>
        ) : (
          <ul className="space-y-1.5">
            {form.bonus_types.map((b) => (
              <li key={b.key}>
                {b.label || b.key}
                <span className="text-muted">
                  {" · "}
                  {b.default_points} pts default
                </span>
              </li>
            ))}
          </ul>
        )}
      </ReviewBlock>

      <ReviewBlock title="Tiebreaks">
        {form.leaderboard_tiebreaks.length === 0 ? (
          <div className="text-muted">None</div>
        ) : (
          <ol className="list-decimal space-y-1 pl-5">
            {form.leaderboard_tiebreaks.map((t, i) => (
              <li key={`${t.metric}-${i}`}>{formatTiebreak(t)}</li>
            ))}
          </ol>
        )}
      </ReviewBlock>

      <ReviewBlock title="Payouts">
        <div>
          Buy-in:{" "}
          {form.buy_in === "" || Number(form.buy_in) === 0 ? "None" : form.buy_in}
        </div>
        {form.payouts.length === 0 ? (
          <div className="text-muted">No prize rows</div>
        ) : (
          <ul className="mt-1 space-y-1.5">
            {form.payouts.map((p, i) => (
              <li key={`${p.phase}-${p.position}-${i}`}>
                {p.label || `#${p.position}`}
                <span className="text-muted">
                  {" · "}
                  {p.phase ? humanizeKey(p.phase) : "overall"}
                  {" · place "}
                  {p.position}
                  {" · "}
                  {p.amount}
                </span>
              </li>
            ))}
          </ul>
        )}
      </ReviewBlock>
    </div>
  );
}

export function TemplateEditor({
  templateId,
  onSaved,
  useHref,
  initialEditing = false,
}: {
  templateId?: string;
  onSaved?: (item: CompetitionTemplate) => void;
  /** When set, show a Use action that continues to league setup. */
  useHref?: string;
  /** Start in edit mode (e.g. after copying a template). */
  initialEditing?: boolean;
}) {
  const { isAdmin } = useAuth();
  const { toast } = useToast();
  const isNew = !templateId || templateId === "new";
  const [form, setForm] = useState<FormState>(structuredClone(blank));
  const [snapshot, setSnapshot] = useState<FormState | null>(null);
  const [canEdit, setCanEdit] = useState(true);
  const [editing, setEditing] = useState(isNew || initialEditing);
  const [stepIndex, setStepIndex] = useState(0);
  const [highestStep, setHighestStep] = useState(0);
  const [stepError, setStepError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!isNew);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const readOnly = !isNew && (!canEdit || !editing);
  const viewing = !isNew && !editing;
  /** Editing an existing template: free jump to any step (including Review). */
  const freeStepNav = !isNew && editing;

  const tabs = BASE_TABS;
  const step = tabs[Math.min(stepIndex, tabs.length - 1)] ?? tabs[0];
  const isFirst = stepIndex === 0;
  const isLast = stepIndex >= tabs.length - 1;
  const reviewIndex = tabs.findIndex((t) => t.id === "review");

  useEffect(() => {
    if (isNew) {
      setForm(structuredClone(blank));
      setSnapshot(null);
      setCanEdit(true);
      setEditing(true);
      setStepIndex(0);
      setHighestStep(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    api<CompetitionTemplate>(`/templates/${templateId}`)
      .then((item) => {
        const next = fromTemplate(item);
        setForm(next);
        setSnapshot(next);
        setCanEdit(Boolean(item.can_edit));
        setEditing(Boolean(item.can_edit) && initialEditing);
        setStepIndex(0);
        // Existing templates: free navigation (viewing, or editing with initialEditing)
        setHighestStep(tabs.length - 1);
      })
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [templateId, isNew, initialEditing, tabs.length]);

  function goToStep(index: number) {
    if (index < 0 || index >= tabs.length) return;
    // Progressive unlock while creating; free jump when editing existing / viewing
    if (!freeStepNav && !viewing && index > highestStep) return;
    setStepError("");
    setStepIndex(index);
  }

  function startEditing() {
    if (!canEdit) return;
    setEditing(true);
    setStepIndex(0);
    setHighestStep(tabs.length - 1);
    setStepError("");
  }

  function cancelEditing() {
    if (snapshot) setForm(structuredClone(snapshot));
    setEditing(false);
    setStepIndex(0);
    setStepError("");
    setHighestStep(tabs.length - 1);
  }

  function validateBasics(): string | null {
    if (!form.label.trim()) return "Enter a template name to continue.";
    const n = form.max_members === "" ? NaN : Number(form.max_members);
    if (!Number.isInteger(n) || n < 2 || n > 100) {
      return "Enter a whole number of managers between 2 and 100.";
    }
    return null;
  }

  function validateCompetitions(): string | null {
    if (form.pool_definitions.length < 1) {
      return "Add at least one competition — leagues need competitions to draft from.";
    }
    return null;
  }

  function goNext() {
    if (!viewing) {
      if (step.id === "basics") {
        const err = validateBasics();
        if (err) {
          setStepError(err);
          return;
        }
      }
      if (step.id === "pools") {
        const err = validateCompetitions();
        if (err) {
          setStepError(err);
          return;
        }
      }
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

  function goToReview() {
    const basicsErr = validateBasics();
    if (basicsErr) {
      setStepIndex(0);
      setStepError(basicsErr);
      return;
    }
    const competitionsErr = validateCompetitions();
    if (competitionsErr) {
      const poolsIndex = tabs.findIndex((t) => t.id === "pools");
      setStepIndex(poolsIndex >= 0 ? poolsIndex : 0);
      setStepError(competitionsErr);
      return;
    }
    setStepError("");
    if (reviewIndex < 0) return;
    setStepIndex(reviewIndex);
    setHighestStep((h) => Math.max(h, reviewIndex));
  }

  async function save(e?: FormEvent) {
    e?.preventDefault();
    if (readOnly) return;
    const basicsErr = validateBasics();
    if (basicsErr) {
      setStepIndex(0);
      setStepError(basicsErr);
      return;
    }
    const competitionsErr = validateCompetitions();
    if (competitionsErr) {
      const poolsIndex = tabs.findIndex((t) => t.id === "pools");
      setStepIndex(poolsIndex >= 0 ? poolsIndex : 0);
      setStepError(competitionsErr);
      return;
    }
    if (form.preassign_mode === "required" && form.preassign_count < 1) {
      setStepIndex(0);
      setStepError("Required preassign mode needs at least 1 team per manager.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const item = await api<CompetitionTemplate>(
        isNew ? "/templates" : `/templates/${templateId}`,
        json(isNew ? "POST" : "PATCH", toWrite(form, isAdmin)),
      );
      const next = fromTemplate(item);
      setForm(next);
      setSnapshot(next);
      toast({
        message: (
          <span className="flex flex-wrap items-center justify-between gap-2">
            <span>Template saved.</span>
            <Link
              href="/leagues/new"
              className="font-bold text-ink underline decoration-brand/50 underline-offset-2 hover:decoration-brand"
            >
              Back to templates
            </Link>
          </span>
        ),
        durationMs: 6000,
        dismissible: true,
      });
      setCanEdit(Boolean(item.can_edit));
      if (!isNew) setEditing(false);
      onSaved?.(item);
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

  async function duplicate() {
    if (!templateId || isNew) return;
    setBusy(true);
    setError("");
    try {
      const item = await api<CompetitionTemplate>(
        `/templates/${templateId}/duplicate`,
        json("POST"),
      );
      toast({ message: `Copied as ${item.label}.` });
      onSaved?.(item);
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

  async function remove() {
    if (!templateId || isNew || readOnly) return;
    setBusy(true);
    setDeleteConfirmOpen(false);
    try {
      await api(`/templates/${templateId}`, json("DELETE"));
      toast({ message: "Deleted." });
      onSaved?.({ id: "" } as CompetitionTemplate);
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

  if (loading) return <Loading label="Loading template" />;

  if (viewing) {
    return (
      <div className="flex flex-col gap-4 animate-in">
        {error && <ErrorState error={error} />}

        <div className="flex flex-wrap items-center gap-2">
          {useHref && (
            <Link
              href={useHref}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-on-brand shadow-sm transition hover:bg-brand-dark"
            >
              <PlayIcon />
              Use template
            </Link>
          )}
          {canEdit && (
            <Button type="button" variant="secondary" onClick={startEditing}>
              <PencilIcon />
              Edit
            </Button>
          )}
          <Button type="button" variant="secondary" disabled={busy} onClick={duplicate}>
            <CopyIcon />
            Copy
          </Button>
        </div>

        <TemplateSettingsSummary form={form} />
      </div>
    );
  }

  return (
    <form
      className="flex flex-col gap-4 animate-in"
      onSubmit={(e) => {
        e.preventDefault();
        if (isLast && !readOnly) void save();
      }}
    >
      {error && <ErrorState error={error} />}

      {!isNew && (
        <div className="flex flex-wrap items-center gap-2">
          {useHref && (
            <Link
              href={useHref}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-on-brand shadow-sm transition hover:bg-brand-dark"
            >
              <PlayIcon />
              Use template
            </Link>
          )}
          {canEdit && (
            <Button type="button" variant="secondary" onClick={cancelEditing}>
              <XIcon />
              Cancel edit
            </Button>
          )}
          <Button type="button" variant="secondary" disabled={busy} onClick={duplicate}>
            <CopyIcon />
            Copy
          </Button>
        </div>
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
            const reached = freeStepNav || i <= highestStep;
            const active = i === stepIndex;
            const canJump = reached && !active;
            return (
              <button
                key={t.id}
                type="button"
                disabled={!canJump && !active}
                onClick={() => goToStep(i)}
                className={cn(
                  "h-1.5 min-w-6 flex-1 rounded-full transition",
                  active ? "bg-brand" : reached ? "bg-brand/35" : "bg-surface-2",
                  canJump && "cursor-pointer hover:bg-brand/60",
                )}
                aria-label={`${t.label}${active ? " (current)" : ""}`}
                aria-current={active ? "step" : undefined}
              />
            );
          })}
        </div>
      </div>

      {stepError && <StatusBanner tone="error">{stepError}</StatusBanner>}

      {step.id === "review" ? (
        <TemplateSettingsSummary form={form} />
      ) : (
      <fieldset disabled={readOnly} className="min-w-0 border-0 p-0">
        <div role="group" aria-label={step.label}>
          {step.id === "basics" && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Label>
                Name
                <Input
                  required
                  value={form.label}
                  onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
                />
              </Label>
              <Label>
                <LabelRow>
                  Managers
                  <FieldHelp label="Managers">
                    Default number of manager seats for leagues created from this template
                    (including the commissioner).
                  </FieldHelp>
                </LabelRow>
                <Input
                  type="number"
                  min={2}
                  max={100}
                  required
                  placeholder="e.g. 8"
                  value={form.max_members}
                  onChange={(e) => {
                    const v = e.target.value;
                    setForm((f) => ({
                      ...f,
                      max_members: v === "" ? "" : Number(v),
                    }));
                  }}
                />
              </Label>
              <div className="flex flex-col gap-1.5 text-sm font-semibold text-muted sm:items-start">
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
                <ChoiceToggle
                  label="Draft style"
                  value={form.draft_style}
                  options={
                    [
                      { id: "linear", label: "Linear" },
                      { id: "snake", label: "Snake" },
                    ] as const
                  }
                  onChange={(draft_style) => setForm((f) => ({ ...f, draft_style }))}
                />
              </div>
              <div
                className={
                  form.preassign_mode !== "off"
                    ? "grid grid-cols-1 gap-3 sm:col-span-2 sm:grid-cols-[minmax(0,1fr)_minmax(6.5rem,8rem)] sm:items-start"
                    : "flex flex-col gap-1.5 text-sm font-semibold text-muted sm:items-start"
                }
              >
                <div className="flex flex-col gap-1.5 text-sm font-semibold text-muted sm:items-start">
                  <LabelRow>
                    Preassign mode
                    <FieldHelp label="Preassign mode">
                      <p className="mb-2">Whether clubs can be assigned before the live draft.</p>
                      <ul className="list-disc space-y-1 pl-4">
                        <li>
                          <strong className="text-ink">Off</strong> — no pre-draft assignments.
                        </li>
                        <li>
                          <strong className="text-ink">Optional</strong> — preassign is available;
                          each manager may have up to the configured number.
                        </li>
                        <li>
                          <strong className="text-ink">Required</strong> — every manager must have
                          exactly the configured number before the draft opens.
                        </li>
                      </ul>
                    </FieldHelp>
                  </LabelRow>
                  <ChoiceToggle
                    label="Preassign mode"
                    value={form.preassign_mode}
                    options={
                      [
                        { id: "off", label: "Off" },
                        { id: "optional", label: "Optional" },
                        { id: "required", label: "Required" },
                      ] as const
                    }
                    onChange={(preassign_mode) =>
                      setForm((f) => ({
                        ...f,
                        preassign_mode,
                        preassign_count:
                          preassign_mode === "required" && f.preassign_count < 1
                            ? 1
                            : f.preassign_count,
                      }))
                    }
                  />
                </div>
                {form.preassign_mode !== "off" && (
                  <Label>
                    Per manager
                    <Input
                      type="number"
                      min={form.preassign_mode === "required" ? 1 : 0}
                      step={1}
                      value={form.preassign_count}
                      onChange={(e) => {
                        const raw = Number(e.target.value);
                        if (!Number.isFinite(raw)) return;
                        const min = form.preassign_mode === "required" ? 1 : 0;
                        setForm((f) => ({
                          ...f,
                          preassign_count: Math.max(min, Math.floor(raw)),
                        }));
                      }}
                    />
                  </Label>
                )}
              </div>
              {isAdmin && (
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2 sm:col-span-2">
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
                competitions={form.pool_definitions.map((p) => ({
                  competition_code: p.competition_code,
                  season_year: p.season_year,
                }))}
              />
            </>
          )}
          {step.id === "pools" && (
            <LeaguePoolsEditor
              value={poolsToEdit(form.pool_definitions)}
              onChange={(rows) =>
                setForm((f) => ({
                  ...f,
                  pool_definitions: poolsFromEdit(rows, f.pool_definitions),
                }))
              }
              managerCapacity={
                form.max_members === "" ? undefined : Number(form.max_members) || undefined
              }
              structureEditable={!readOnly}
              showHeading={false}
              rosterClubOrder={form.roster_club_order}
              onRosterClubOrderChange={(roster_club_order) =>
                setForm((f) => ({ ...f, roster_club_order }))
              }
            />
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
                Manual or season-end bonus categories (for example winner’s bonus or player of
                the season). When awarding later, commissioners can apply a type to a team, a
                match (one side of a fixture), or a roster/manager directly.
              </StepTip>
              <BonusTypesListEditor
                value={form.bonus_types}
                onChange={(bonus_types) => setForm((f) => ({ ...f, bonus_types }))}
                readOnly={readOnly}
                emptyHint="Add bonus categories to seed onto leagues created from this template."
              />
            </>
          )}
          {step.id === "payouts" && (
            <div className="flex flex-col gap-4">
              <StepTip label="Payouts">
                Entry buy-in and prize amounts by phase and finishing place. Leave buy-in empty for
                none.
              </StepTip>
              <Label className="max-w-xs">
                <LabelRow>
                  Buy-in
                  <FieldHelp label="Buy-in">
                    Entry amount seeded onto leagues from this template. Leave empty for none.
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
        </div>
      </fieldset>
      )}

      <Stack gap="sm">
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" disabled={isFirst} onClick={goBack}>
              Back
            </Button>
            {!isLast && (
              <Button type="button" variant="primary" onClick={goNext}>
                Next
              </Button>
            )}
            {freeStepNav && !isLast && (
              <Button type="button" variant="secondary" onClick={goToReview}>
                Review & save
              </Button>
            )}
            {isLast && !readOnly && (
              <IconButton type="submit" label="Save template" variant="primary" busy={busy}>
                <SaveIcon />
              </IconButton>
            )}
          </div>
          {!isNew && editing && (
            <IconButton
              type="button"
              label="Delete template"
              variant="danger"
              busy={busy}
              onClick={() => setDeleteConfirmOpen(true)}
            >
              <TrashIcon />
            </IconButton>
          )}
        </div>
      </Stack>

      <ConfirmDialog
        open={deleteConfirmOpen}
        title="Delete this template?"
        description="This permanently removes the template. Leagues already created from it are not affected."
        confirmLabel="Delete template"
        cancelLabel="Keep template"
        tone="danger"
        onCancel={() => setDeleteConfirmOpen(false)}
        onConfirm={() => {
          void remove();
        }}
      />
    </form>
  );
}
