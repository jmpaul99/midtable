/** Shared scoring / template config shapes + normalize helpers. */

export type ResultPoints = {
  win: number;
  draw: number;
  loss: number;
};

export type UpsetThreshold = {
  key: string;
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

export function normalizeResultPoints(raw: unknown): ResultPoints {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  return {
    win: num(o.win, 3),
    draw: num(o.draw, 1),
    loss: num(o.loss, 0),
  };
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
    return {
      key: str(t.key, `threshold_${i + 1}`),
      result: (result === "draw" || result === "loss" ? result : "win") as UpsetThreshold["result"],
      min_gap: num(t.min_gap ?? t.minimum_position_gap, 0),
      max_gap:
        t.max_gap == null && t.maximum_position_gap == null
          ? null
          : num(t.max_gap ?? t.maximum_position_gap, 0),
      points: num(t.points ?? t.bonus, 0),
    };
  });
  return {
    enabled: o.enabled !== false,
    rank_source: str(o.rank_source, "league_table_at_kickoff"),
    ranking_list_key: o.ranking_list_key == null ? null : str(o.ranking_list_key),
    min_played: num(eligibility.min_played ?? o.min_played, 8),
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
    thresholds: rules.thresholds.map((t) => ({
      key: t.key,
      result: t.result,
      min_gap: t.min_gap,
      max_gap: t.max_gap,
      points: t.points,
    })),
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
  return arr(raw).map((item) => {
    if (typeof item === "string") {
      if (item === "upset_points") {
        return {
          metric: "event_points",
          direction: "desc" as const,
          event_types: ["minor_upset", "major_upset", "major_upset_draw"],
          bonus_type_keys: [],
        };
      }
      if (item === "win_count") {
        return {
          metric: "event_count",
          direction: "desc" as const,
          event_types: ["win"],
          bonus_type_keys: [],
        };
      }
      return {
        metric: item,
        direction: "desc" as const,
        event_types: [],
        bonus_type_keys: [],
      };
    }
    const t = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    return {
      metric: str(t.metric, "total_points"),
      direction: str(t.direction, "desc") === "asc" ? ("asc" as const) : ("desc" as const),
      event_types: arr(t.event_types).map((s) => str(s)),
      bonus_type_keys: arr(t.bonus_type_keys).map((s) => str(s)),
    };
  });
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
