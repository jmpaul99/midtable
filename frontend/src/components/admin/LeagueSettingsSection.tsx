"use client";

import { FormEvent, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { Bonus, League, PoolTeam } from "@/lib/types";
import { StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { SaveIcon } from "@/components/ui/icons";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { BonusesSection } from "./BonusesSection";
import type { BonusTypeRow } from "./useAdminLeagueData";
import {
  eventOptionsFromUpsetKeys,
  normalizeResultPoints,
  normalizeTiebreaks,
  normalizeUpsetRules,
  ResultPointsEditor,
  serializeUpsetRules,
  TiebreaksEditor,
  UpsetRulesEditor,
  type ResultPoints,
  type TiebreakRung,
  type UpsetRules,
} from "@/components/settings";

type Tab = "points" | "upsets" | "tiebreaks" | "bonuses";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "points", label: "Points" },
  { id: "upsets", label: "Upsets" },
  { id: "tiebreaks", label: "Tiebreaks" },
  { id: "bonuses", label: "Bonuses" },
];

export function LeagueSettingsSection({
  league,
  bonusTypes = [],
  bonuses,
  allTeams = [],
  onAction,
  onSaved,
}: {
  league: League;
  bonusTypes?: BonusTypeRow[];
  bonuses?: Bonus[];
  allTeams?: Array<{ team: PoolTeam; pool: League["pools"][number] }>;
  onAction?: (path: string, method: string, body?: unknown) => Promise<unknown>;
  onSaved?: () => void;
}) {
  const [tab, setTab] = useState<Tab>("points");
  const [resultPoints, setResultPoints] = useState<ResultPoints>(() =>
    normalizeResultPoints(league.result_points),
  );
  const [upsetRules, setUpsetRules] = useState<UpsetRules>(() =>
    normalizeUpsetRules(league.upset_rules),
  );
  const [tiebreaks, setTiebreaks] = useState<TiebreakRung[]>(() =>
    normalizeTiebreaks(league.leaderboard_tiebreaks),
  );
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(
        `/leagues/${league.id}/settings`,
        json("PATCH", {
          result_points: resultPoints,
          upset_rules: serializeUpsetRules(upsetRules),
          leaderboard_tiebreaks: tiebreaks.map((t) => ({
            metric: t.metric,
            direction: t.direction,
            ...(t.event_types.length ? { event_types: t.event_types } : {}),
            ...(t.bonus_type_keys.length ? { bonus_type_keys: t.bonus_type_keys } : {}),
          })),
        }),
      );
      setMessage("Scoring settings saved. If values changed, run Recompute scores.");
      onSaved?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <Stack>
        <Muted>
          Points, upsets, tiebreaks, and bonuses. Changing scoring after matches exist requires a
          recompute.
        </Muted>
        {error && <StatusBanner tone="error">{error}</StatusBanner>}
        {message && <StatusBanner tone="success">{message}</StatusBanner>}

        <div
          className="flex gap-1 overflow-x-auto rounded-xl bg-surface-2 p-1"
          role="tablist"
          aria-label="Scoring settings"
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

        {tab === "bonuses" ? (
          <div role="tabpanel">
            {onAction ? (
              <BonusesSection
                leagueId={league.id}
                bonusTypes={bonusTypes}
                bonuses={bonuses}
                allTeams={allTeams}
                onAction={onAction}
                embedded
              />
            ) : (
              <Muted>Bonus actions unavailable.</Muted>
            )}
          </div>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={save}>
            <div role="tabpanel">
              {tab === "points" && (
                <ResultPointsEditor value={resultPoints} onChange={setResultPoints} />
              )}
              {tab === "upsets" && (
                <UpsetRulesEditor
                  value={upsetRules}
                  onChange={setUpsetRules}
                  allowCustomLists={(league.pools?.length ?? 0) > 0}
                />
              )}
              {tab === "tiebreaks" && (
                <TiebreaksEditor
                  value={tiebreaks}
                  onChange={setTiebreaks}
                  eventTypeOptions={eventOptionsFromUpsetKeys(
                    upsetRules.thresholds.map((t) => ({ key: t.key, name: t.name })),
                  )}
                  bonusTypeOptions={bonusTypes.map((b) => ({
                    value: b.key,
                    label: b.label || b.key,
                  }))}
                />
              )}
            </div>

            <div className="flex justify-start">
              <IconButton type="submit" label="Save scoring settings" variant="primary" busy={busy}>
                <SaveIcon />
              </IconButton>
            </div>
          </form>
        )}
      </Stack>
    </Card>
  );
}
