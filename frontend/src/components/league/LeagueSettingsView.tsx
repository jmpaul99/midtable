"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { League } from "@/lib/types";
import { api } from "@/lib/api";
import { formatDateTimeWithZone } from "@/lib/format";
import { Card, Muted, Stack } from "@/components/ui/Card";
import {
  normalizePayouts,
  normalizePhases,
  normalizeResultPoints,
  normalizeTiebreaks,
  normalizeUpsetRules,
  type LeaderboardPhase,
  type TiebreakRung,
} from "@/components/settings";

type BonusTypeSummary = {
  key: string;
  label: string;
  default_points: number;
  sort_order?: number;
};

function ReviewBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-0 max-w-full overflow-hidden rounded-xl border border-line bg-surface-2/40 px-3 py-2.5">
      <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-muted">{title}</h4>
      <div className="min-w-0 space-y-0.5 font-semibold text-ink">{children}</div>
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

function tiebreakRuleLabel(
  r: TiebreakRung,
  resolveBonus: (key: string) => string,
  resolveEvent: (key: string) => string,
): string {
  const kind =
    r.metric === "event_count" || r.metric === "bonus_count"
      ? "count"
      : r.metric === "event_points" || r.metric === "bonus_points"
        ? "points"
        : null;

  if (r.event_types.length && kind) {
    return `${r.event_types.map(resolveEvent).join(" + ")} (${kind})`;
  }
  if (r.bonus_type_keys.length && kind) {
    return `${r.bonus_type_keys.map(resolveBonus).join(" + ")} (${kind})`;
  }
  if (r.metric === "total_points") return "Total points";
  return humanizeKey(r.metric);
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

export function LeagueSettingsView({ league }: { league: League }) {
  const [bonusTypes, setBonusTypes] = useState<BonusTypeSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    api<BonusTypeSummary[]>(`/leagues/${league.id}/bonus-types`)
      .then((rows) => {
        if (cancelled) return;
        setBonusTypes(
          [...rows].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)),
        );
      })
      .catch(() => {
        if (!cancelled) setBonusTypes([]);
      });
    return () => {
      cancelled = true;
    };
  }, [league.id]);

  const phases = useMemo(
    () => normalizePhases(league.leaderboard_phases),
    [league.leaderboard_phases],
  );
  const payouts = useMemo(() => {
    const rows = normalizePayouts(league.payouts);
    const isOverall = (phase: string) =>
      !phase || phase === "season" || phase === "total" || phase === "season_total";
    return [...rows].sort((a, b) => {
      const aOverall = isOverall(a.phase) ? 0 : 1;
      const bOverall = isOverall(b.phase) ? 0 : 1;
      if (aOverall !== bOverall) return aOverall - bOverall;
      if (a.phase !== b.phase) return a.phase.localeCompare(b.phase);
      return a.position - b.position;
    });
  }, [league.payouts]);
  const resultPoints = useMemo(
    () => normalizeResultPoints(league.result_points),
    [league.result_points],
  );
  const upsetRules = useMemo(
    () => normalizeUpsetRules(league.upset_rules),
    [league.upset_rules],
  );
  const tiebreaks = useMemo(
    () => normalizeTiebreaks(league.leaderboard_tiebreaks),
    [league.leaderboard_tiebreaks],
  );

  const pools = useMemo(
    () =>
      [...(league.pools || [])].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)),
    [league.pools],
  );
  const buyIn = Number(league.buy_in ?? 0);
  const memberCount = league.members?.length ?? 0;
  const bonusKeys = league.bonus_type_keys || [];
  const stages = Object.entries(resultPoints.by_stage || {});
  const hasEtPk =
    resultPoints.win_et != null ||
    resultPoints.loss_et != null ||
    resultPoints.win_pk != null ||
    resultPoints.loss_pk != null;
  const preassign = league.preassign_mode || "off";
  const preassignCount =
    league.preassign_count ??
    (typeof league.settings?.preassign_count === "number"
      ? league.settings.preassign_count
      : undefined);

  const phaseLabelByKey = useMemo(() => {
    const map = new Map<string, string>();
    map.set("season", "Overall");
    for (const p of league.phases || []) {
      if (p.key) map.set(p.key, p.name || p.key);
    }
    for (const p of phases) {
      if (p.key) map.set(p.key, p.label || p.key);
    }
    return map;
  }, [league.phases, phases]);

  function phaseLabel(key: string | null | undefined): string {
    if (!key) return "Overall";
    return phaseLabelByKey.get(key) ?? "Overall";
  }

  const bonusLabelByKey = useMemo(() => {
    const map = new Map<string, string>();
    for (const b of bonusTypes) {
      if (b.key) map.set(b.key, b.label || b.key);
    }
    return map;
  }, [bonusTypes]);

  function bonusLabel(key: string): string {
    return bonusLabelByKey.get(key) || humanizeKey(key);
  }

  const eventLabelByKey = useMemo(() => {
    const map = new Map<string, string>();
    for (const t of upsetRules.thresholds) {
      if (t.key) map.set(t.key, t.name || t.key);
    }
    return map;
  }, [upsetRules.thresholds]);

  function eventLabel(key: string): string {
    return eventLabelByKey.get(key) || humanizeKey(key);
  }

  const bonusRows =
    bonusTypes.length > 0
      ? bonusTypes
      : bonusKeys.map((key) => ({
          key,
          label: humanizeKey(key),
          default_points: null as number | null,
        }));
  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <Stack className="min-w-0">
        <Muted>How this league is set up — scoring, competitions, and prizes.</Muted>

        <div className="flex min-w-0 flex-col gap-3 text-sm">
          <ReviewBlock title="Basics">
            <div className="text-base">{league.name || "—"}</div>
            <div>Season: {league.season_label || "—"}</div>
            <div>
              Managers: {memberCount}
              {league.max_members != null ? ` of ${league.max_members}` : ""}
            </div>
          </ReviewBlock>

          <ReviewBlock title="Draft">
            <div>Status: {humanizeKey(league.status || "unknown")}</div>
            <div>
              Style: {league.draft_style === "snake" ? "Snake" : "Linear"}
            </div>
            <div>
              Preassign clubs before draft:{" "}
              {preassign === "off" || preassign === "none"
                ? "Off"
                : preassign === "required" || preassign === "supported"
                  ? preassignCount != null
                    ? `Required (${preassignCount})`
                    : "Required"
                  : preassign === "optional"
                    ? preassignCount != null
                      ? `Optional (max ${preassignCount})`
                      : "Optional"
                    : humanizeKey(preassign)}
            </div>
            <div>
              Scheduled start:{" "}
              {league.draft_scheduled_at
                ? formatDateTimeWithZone(league.draft_scheduled_at)
                : typeof league.settings?.draft_scheduled_at === "string"
                  ? formatDateTimeWithZone(league.settings.draft_scheduled_at)
                  : "Not set (open manually)"}
            </div>
            <div>
              Pick timer:{" "}
              {league.pick_timer_seconds != null && league.pick_timer_seconds > 0
                ? `${league.pick_timer_seconds}s`
                : typeof league.settings?.pick_timer_seconds === "number" &&
                    league.settings.pick_timer_seconds > 0
                  ? `${league.settings.pick_timer_seconds}s`
                  : "Off"}
            </div>
          </ReviewBlock>

          <ReviewBlock title="Competitions">
            {pools.length === 0 ? (
              <div className="text-muted">None</div>
            ) : (
              <ul className="space-y-2">
                {pools.map((p) => (
                  <li
                    key={p.id || p.key}
                    className="border-t border-line/60 pt-2 first:border-0 first:pt-0"
                  >
                    <div>{p.label || p.key}</div>
                    <div className="text-muted">
                      {[
                        p.competition_code || null,
                        p.season_year ? String(p.season_year) : null,
                        `${p.slot_count ?? 1} slot${(p.slot_count ?? 1) === 1 ? "" : "s"}`,
                        p.scores_match_results !== false
                          ? "scores results"
                          : "no result scoring",
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
              Win {resultPoints.win} · Draw {resultPoints.draw} · Loss {resultPoints.loss}
            </div>
            {hasEtPk && (
              <div className="mt-1 space-y-0.5 text-muted">
                {pointLine("Win (ET)", resultPoints.win_et, String(resultPoints.win))}
                {pointLine("Loss (ET)", resultPoints.loss_et, String(resultPoints.loss))}
                {pointLine("Win (PK)", resultPoints.win_pk, String(resultPoints.win))}
                {pointLine("Loss (PK)", resultPoints.loss_pk, String(resultPoints.loss))}
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
            {upsetRules.enabled ? (
              <>
                <div>
                  Enabled ·{" "}
                  {upsetRules.rank_source === "fixed_ranking_at_event_start"
                    ? "Fixed ranking list"
                    : "League table at kickoff"}
                  {upsetRules.rank_source === "fixed_ranking_at_event_start" &&
                    upsetRules.ranking_list_key && (
                      <> · {humanizeKey(upsetRules.ranking_list_key)}</>
                    )}
                </div>
                {upsetRules.min_played > 0 && (
                  <div className="text-muted">
                    Min games played before upset scoring starts: {upsetRules.min_played}
                  </div>
                )}
                {upsetRules.thresholds.length === 0 ? (
                  <div className="text-muted">No thresholds</div>
                ) : (
                  <ul className="mt-1 space-y-1.5">
                    {upsetRules.thresholds.map((t) => (
                      <li
                        key={t.key}
                        className="border-t border-line/60 pt-1.5 first:border-0 first:pt-0"
                      >
                        <div>{t.name || humanizeKey(t.key)}</div>
                        <div className="text-muted">
                          {humanizeKey(t.result)}
                          {upsetRules.rank_source === "fixed_ranking_at_event_start"
                            ? " · gap in rankings "
                            : " · gap in table "}
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
            {phases.length === 0 ? (
              <div className="text-muted">None</div>
            ) : (
              <ul className="space-y-2">
                {phases.map((p) => (
                  <li
                    key={p.key}
                    className="border-t border-line/60 pt-2 first:border-0 first:pt-0"
                  >
                    <div>{p.label || p.key}</div>
                    <div className="text-muted">{formatPhaseFilter(p.match_filter)}</div>
                    {p.include_bonus_types.length > 0 && (
                      <div className="text-muted">
                        Bonuses: {p.include_bonus_types.map(bonusLabel).join(", ")}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </ReviewBlock>

          <ReviewBlock title="Bonuses">
            {bonusRows.length === 0 ? (
              <div className="text-muted">None</div>
            ) : (
              <ul className="space-y-1.5">
                {bonusRows.map((b) => (
                  <li key={b.key}>
                    {b.label || humanizeKey(b.key)}
                    {b.default_points != null && (
                      <span className="text-muted">
                        {" · "}
                        {b.default_points} pts
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </ReviewBlock>

          <ReviewBlock title="Tiebreakers">
            {tiebreaks.length === 0 ? (
              <div className="text-muted">None</div>
            ) : (
              <div className="max-w-full overflow-x-auto overscroll-x-contain rounded-lg border border-line [scrollbar-width:thin]">
                <table className="w-full min-w-[18rem] text-left text-sm">
                  <thead className="border-b border-line text-xs font-bold uppercase tracking-wide text-muted">
                    <tr>
                      <th className="px-3 py-2 font-bold">#</th>
                      <th className="px-3 py-2 font-bold">Filter</th>
                      <th className="whitespace-nowrap px-3 py-2 font-bold">Order</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tiebreaks.map((t, i) => (
                      <tr
                        key={`${t.metric}-${i}`}
                        className="border-b border-line last:border-0"
                      >
                        <td className="px-3 py-2.5 tabular-nums">{i + 1}</td>
                        <td className="whitespace-nowrap px-3 py-2.5">
                          {tiebreakRuleLabel(t, bonusLabel, eventLabel)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-muted">
                          {t.direction === "asc" ? "Low → high" : "High → low"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </ReviewBlock>

          <ReviewBlock title="Payouts">
            <div>Buy-in: {buyIn === 0 ? "None" : buyIn}</div>
            {payouts.length === 0 ? (
              <div className="text-muted">No prize rows</div>
            ) : (
              <div className="mt-2 max-w-full overflow-x-auto overscroll-x-contain rounded-lg border border-line [scrollbar-width:thin]">
                <table className="w-full min-w-[20rem] text-left text-sm">
                  <thead className="border-b border-line text-xs font-bold uppercase tracking-wide text-muted">
                    <tr>
                      <th className="px-3 py-2 font-bold">Prize</th>
                      <th className="px-3 py-2 font-bold">Phase</th>
                      <th className="whitespace-nowrap px-3 py-2 text-right font-bold">Place</th>
                      <th className="whitespace-nowrap px-3 py-2 text-right font-bold">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payouts.map((p, i) => (
                      <tr
                        key={`${p.phase}-${p.position}-${i}`}
                        className="border-b border-line last:border-0"
                      >
                        <td className="whitespace-nowrap px-3 py-2.5">
                          {p.label || `#${p.position}`}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-muted">
                          {phaseLabel(p.phase)}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{p.position}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{p.amount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </ReviewBlock>
        </div>
      </Stack>
    </Card>
  );
}
