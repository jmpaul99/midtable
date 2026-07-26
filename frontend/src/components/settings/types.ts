/** Shared scoring / template config shapes + normalize helpers. */

export type ResultPointKey =
  | "win"
  | "draw"
  | "loss"
  | "win_et"
  | "loss_et"
  | "win_pk"
  | "loss_pk";

export const RESULT_POINT_KEYS: ResultPointKey[] = [
  "win",
  "draw",
  "loss",
  "win_et",
  "loss_et",
  "win_pk",
  "loss_pk",
];

export const BASE_RESULT_KEYS = ["win", "draw", "loss"] as const;
export const OVERTIME_RESULT_KEYS = ["win_et", "loss_et", "win_pk", "loss_pk"] as const;

/** Sparse per-stage overrides; null means inherit. */
export type StageResultPoints = {
  win: number | null;
  draw: number | null;
  loss: number | null;
  win_et: number | null;
  loss_et: number | null;
  win_pk: number | null;
  loss_pk: number | null;
};

/** Optional ET/PK fields: null means inherit win / loss. */
export type ResultPoints = {
  win: number;
  draw: number;
  loss: number;
  win_et: number | null;
  loss_et: number | null;
  win_pk: number | null;
  loss_pk: number | null;
  by_stage: Record<string, StageResultPoints>;
};

export const EMPTY_STAGE_RESULT_POINTS: StageResultPoints = {
  win: null,
  draw: null,
  loss: null,
  win_et: null,
  loss_et: null,
  win_pk: null,
  loss_pk: null,
};

export type UpsetThreshold = {
  /** Stable machine id for scoring / tiebreaks / match events. System-generated. */
  key: string;
  /** User-facing label. */
  name: string;
  result: "win" | "draw" | "loss";
  min_gap: number;
  max_gap: number | null;
  points: number;
};

export type UpsetRules = {
  enabled: boolean;
  rank_source: "league_table_at_kickoff" | "fixed_ranking_at_event_start" | string;
  ranking_list_key: string | null;
  min_played: number;
  thresholds: UpsetThreshold[];
};

export type PhaseMatchFilter =
  | { type: "matchweek_range"; from: number; to: number }
  | { type: "stage_in"; stages: string[] };

export type LeaderboardPhase = {
  key: string;
  label: string;
  match_filter: PhaseMatchFilter;
  include_bonus_types: string[];
};

export type TiebreakRung = {
  metric: string;
  direction: "asc" | "desc";
  event_types: string[];
  bonus_type_keys: string[];
};

export type PayoutRow = {
  label: string;
  phase: string;
  position: number;
  amount: number;
};

export type PoolDefinition = {
  key: string;
  label: string;
  scores_match_results: boolean;
  slot_count: number;
  sort_order: number;
  provider: string;
  competition_code: string;
  season_year: number;
  tie_break_order: string[];
};

export type BonusTypeDef = {
  key: string;
  label: string;
  default_points: number;
  sort_order: number;
};

export type RosterSlot = {
  pool_key: string;
  count: number;
  label: string;
};

function num(v: unknown, fallback: number): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : v == null ? fallback : String(v);
}

function arr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function optionalNum(o: Record<string, unknown>, key: string): number | null {
  if (!(key in o) || o[key] == null || o[key] === "") return null;
  const n = Number(o[key]);
  return Number.isFinite(n) ? n : null;
}

function normalizeStageResultPoints(raw: unknown): StageResultPoints {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  return {
    win: optionalNum(o, "win"),
    draw: optionalNum(o, "draw"),
    loss: optionalNum(o, "loss"),
    win_et: optionalNum(o, "win_et"),
    loss_et: optionalNum(o, "loss_et"),
    win_pk: optionalNum(o, "win_pk"),
    loss_pk: optionalNum(o, "loss_pk"),
  };
}

function serializeStageResultPoints(value: StageResultPoints): Record<string, number> | null {
  const out: Record<string, number> = {};
  for (const key of RESULT_POINT_KEYS) {
    const v = value[key];
    if (v != null) out[key] = v;
  }
  return Object.keys(out).length ? out : null;
}

export function normalizeResultPoints(raw: unknown): ResultPoints {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const byStageRaw =
    o.by_stage && typeof o.by_stage === "object" && !Array.isArray(o.by_stage)
      ? (o.by_stage as Record<string, unknown>)
      : {};
  const by_stage: Record<string, StageResultPoints> = {};
  for (const [code, stageCfg] of Object.entries(byStageRaw)) {
    const key = code.trim();
    if (!key) continue;
    const stage = normalizeStageResultPoints(stageCfg);
    if (RESULT_POINT_KEYS.some((k) => stage[k] != null)) {
      by_stage[key] = stage;
    }
  }
  return {
    win: num(o.win, 3),
    draw: num(o.draw, 1),
    loss: num(o.loss, 0),
    win_et: optionalNum(o, "win_et"),
    loss_et: optionalNum(o, "loss_et"),
    win_pk: optionalNum(o, "win_pk"),
    loss_pk: optionalNum(o, "loss_pk"),
    by_stage,
  };
}

export type SerializedResultPoints = {
  win: number;
  draw: number;
  loss: number;
  win_et?: number;
  loss_et?: number;
  win_pk?: number;
  loss_pk?: number;
  by_stage?: Record<string, Record<string, number>>;
};

/** Persist only set ET/PK / stage overrides; omit null so the engine inherits. */
export function serializeResultPoints(value: ResultPoints): SerializedResultPoints {
  const out: SerializedResultPoints = {
    win: value.win,
    draw: value.draw,
    loss: value.loss,
  };
  if (value.win_et != null) out.win_et = value.win_et;
  if (value.loss_et != null) out.loss_et = value.loss_et;
  if (value.win_pk != null) out.win_pk = value.win_pk;
  if (value.loss_pk != null) out.loss_pk = value.loss_pk;
  const byStage: Record<string, Record<string, number>> = {};
  for (const [code, stage] of Object.entries(value.by_stage || {})) {
    const serialized = serializeStageResultPoints(stage);
    if (serialized) byStage[code] = serialized;
  }
  if (Object.keys(byStage).length) out.by_stage = byStage;
  return out;
}

export function hasOvertimeOverrides(value: ResultPoints): boolean {
  return (
    value.win_et != null ||
    value.loss_et != null ||
    value.win_pk != null ||
    value.loss_pk != null
  );
}

export function hasStageOverrides(value: ResultPoints): boolean {
  return Object.values(value.by_stage || {}).some((s) => stageOverrideKeys(s).length > 0);
}

export function stageOverrideCount(value: ResultPoints): number {
  return Object.values(value.by_stage || {}).filter((s) => stageOverrideKeys(s).length > 0)
    .length;
}

export function stageHasOvertimeOverrides(stage: StageResultPoints): boolean {
  return OVERTIME_RESULT_KEYS.some((k) => stage[k] != null);
}

export function stageOverrideKeys(stage: StageResultPoints | undefined): ResultPointKey[] {
  if (!stage) return [];
  return RESULT_POINT_KEYS.filter((k) => stage[k] != null);
}

/** Default-block resolved values (ET/PK inherit Default win/loss when unset). */
export function defaultResolvedPoints(
  value: ResultPoints,
): Record<ResultPointKey, number> {
  return {
    win: value.win,
    draw: value.draw,
    loss: value.loss,
    win_et: value.win_et ?? value.win,
    loss_et: value.loss_et ?? value.loss,
    win_pk: value.win_pk ?? value.win,
    loss_pk: value.loss_pk ?? value.loss,
  };
}

/** Resolved points for a stage; empty stage fields always use Default. */
export function resolveResultPoints(
  value: ResultPoints,
  stage?: string | null,
): Record<ResultPointKey, number> {
  const defaults = defaultResolvedPoints(value);
  const stagePts = stage ? value.by_stage[stage] : undefined;
  if (!stagePts) return defaults;
  return {
    win: stagePts.win ?? defaults.win,
    draw: stagePts.draw ?? defaults.draw,
    loss: stagePts.loss ?? defaults.loss,
    win_et: stagePts.win_et ?? defaults.win_et,
    loss_et: stagePts.loss_et ?? defaults.loss_et,
    win_pk: stagePts.win_pk ?? defaults.win_pk,
    loss_pk: stagePts.loss_pk ?? defaults.loss_pk,
  };
}

/** Slugify a display name into a candidate machine key. */
export function slugifyKey(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 40);
}

/** Ensure a unique key among siblings. */
export function uniqueKey(
  base: string,
  existingKeys: string[],
  selfIndex?: number,
  fallback = "item",
): string {
  const root = base || fallback;
  let candidate = root;
  let n = 2;
  while (existingKeys.some((k, i) => k === candidate && i !== selfIndex)) {
    candidate = `${root}_${n++}`;
  }
  return candidate;
}

/** Map threshold key → display name. */
export function upsetNameByKey(raw: unknown): Record<string, string> {
  return Object.fromEntries(
    normalizeUpsetRules(raw).thresholds.map((t) => [t.key, t.name || t.key]),
  );
}

export function normalizeUpsetRules(raw: unknown): UpsetRules {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const eligibility =
    o.eligibility && typeof o.eligibility === "object"
      ? (o.eligibility as Record<string, unknown>)
      : {};
  const thresholds = arr(o.thresholds).map((item, i) => {
    const t = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    const result = str(t.result, "win");
    const key = str(t.key, `threshold_${i + 1}`);
    const name = str(t.name, "") || key;
    return {
      key,
      name,
      result: (result === "draw" || result === "loss" ? result : "win") as UpsetThreshold["result"],
      min_gap: num(t.min_gap, 0),
      max_gap: t.max_gap == null ? null : num(t.max_gap, 0),
      points: num(t.points, 0),
    };
  });
  return {
    enabled: o.enabled !== false,
    rank_source: str(o.rank_source, "league_table_at_kickoff"),
    ranking_list_key: o.ranking_list_key == null ? null : str(o.ranking_list_key),
    min_played: num(eligibility.min_played ?? o.min_played, 0),
    thresholds,
  };
}

/** Serialize upset rules into the API shape (eligibility nested). */
export function serializeUpsetRules(rules: UpsetRules): Record<string, unknown> {
  return {
    enabled: rules.enabled,
    rank_source: rules.rank_source,
    ranking_list_key:
      rules.rank_source === "fixed_ranking_at_event_start" ? rules.ranking_list_key : null,
    eligibility: { min_played: rules.min_played },
    thresholds: rules.thresholds.map((t, i) => {
      const name = (t.name ?? "").trim() || (t.key ?? "").trim() || `upset_${i + 1}`;
      const key =
        (t.key ?? "").trim() ||
        uniqueKey(
          slugifyKey(name) || `upset_${i + 1}`,
          rules.thresholds.map((x) => x.key),
          i,
          "upset",
        );
      return {
        key,
        name,
        result: t.result,
        min_gap: t.min_gap,
        max_gap: t.max_gap,
        points: t.points,
      };
    }),
  };
}

export function normalizePhases(raw: unknown): LeaderboardPhase[] {
  return arr(raw).map((item, i) => {
    const p = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    const mf = (p.match_filter && typeof p.match_filter === "object"
      ? p.match_filter
      : {}) as Record<string, unknown>;
    const type = str(mf.type, "matchweek_range");
    const match_filter: PhaseMatchFilter =
      type === "stage_in"
        ? {
            type: "stage_in",
            stages: arr(mf.stages).map((s) => str(s)),
          }
        : {
            type: "matchweek_range",
            from: num(mf.from, 1),
            to: num(mf.to, 19),
          };
    return {
      key: str(p.key, `phase_${i + 1}`),
      label: str(p.label, str(p.key, `Phase ${i + 1}`)),
      match_filter,
      include_bonus_types: arr(p.include_bonus_types).map((s) => str(s)),
    };
  });
}

export function normalizeTiebreaks(raw: unknown): TiebreakRung[] {
  return arr(raw)
    .filter((item): item is Record<string, unknown> => !!item && typeof item === "object")
    .map((t) => ({
      metric: str(t.metric, "total_points"),
      direction: str(t.direction, "desc") === "asc" ? ("asc" as const) : ("desc" as const),
      event_types: arr(t.event_types).map((s) => str(s)),
      bonus_type_keys: arr(t.bonus_type_keys).map((s) => str(s)),
    }));
}

export function normalizePayouts(raw: unknown): PayoutRow[] {
  return arr(raw).map((item, i) => {
    const p = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    return {
      label: str(p.label, `Payout ${i + 1}`),
      phase: str(p.phase, "season"),
      position: num(p.position, 1),
      amount: num(p.amount, 0),
    };
  });
}

export function normalizePoolDefinitions(raw: unknown): PoolDefinition[] {
  return arr(raw).map((item, i) => {
    const p = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    return {
      key: str(p.key, `pool_${i + 1}`),
      label: str(p.label, str(p.key, `Pool ${i + 1}`)),
      scores_match_results: p.scores_match_results !== false,
      slot_count: num(p.slot_count, 1),
      sort_order: num(p.sort_order, i + 1),
      provider: str(p.provider, "football-data.org"),
      competition_code: str(p.competition_code, ""),
      season_year: num(p.season_year, new Date().getFullYear()),
      tie_break_order: arr(p.tie_break_order).length
        ? arr(p.tie_break_order).map((s) => str(s))
        : ["points", "gd", "gf", "name"],
    };
  });
}

export function normalizeBonusTypes(raw: unknown): BonusTypeDef[] {
  return arr(raw).map((item, i) => {
    const b = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    return {
      key: str(b.key, `bonus_${i + 1}`),
      label: str(b.label, str(b.key, `Bonus ${i + 1}`)),
      default_points: num(b.default_points ?? b.points, 0),
      sort_order: num(b.sort_order, i + 1),
    };
  });
}

export function normalizeRosterSlots(raw: unknown): RosterSlot[] {
  return arr(raw).map((item, i) => {
    const r = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    return {
      pool_key: str(r.pool_key, ""),
      count: num(r.count, 1),
      label: str(r.label, `Slot ${i + 1}`),
    };
  });
}

export function parseCommaList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function joinCommaList(values: string[]): string {
  return values.join(", ");
}
