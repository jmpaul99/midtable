"use client";

import { FormEvent, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type { Bonus, League, Manager, PoolTeam } from "@/lib/types";
import { IconButton } from "@/components/ui/IconButton";
import { SaveIcon } from "@/components/ui/icons";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { useToast } from "@/components/ui/ToastProvider";
import { cn } from "@/lib/cn";
import { BonusesSection } from "./BonusesSection";
import type { BonusTypeRow } from "./useAdminLeagueData";
import {
  eventOptionsFromUpsetKeys,
  normalizeResultPoints,
  normalizeTiebreaks,
  normalizeUpsetRules,
  ResultPointsEditor,
  serializeResultPoints,
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
  members = [],
  onAction,
  onSaved,
}: {
  league: League;
  bonusTypes?: BonusTypeRow[];
  bonuses?: Bonus[];
  allTeams?: Array<{ team: PoolTeam; pool: League["pools"][number] }>;
  members?: Manager[];
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
  const [busy, setBusy] = useState(false);
  const { toast } = useToast();

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api(
        `/leagues/${league.id}/settings`,
        json("PATCH", {
          result_points: serializeResultPoints(resultPoints),
          upset_rules: serializeUpsetRules(upsetRules),
          leaderboard_tiebreaks: tiebreaks.map((t) => ({
            metric: t.metric,
            direction: t.direction,
            ...(t.event_types.length ? { event_types: t.event_types } : {}),
            ...(t.bonus_type_keys.length ? { bonus_type_keys: t.bonus_type_keys } : {}),
          })),
        }),
      );
      toast({
        message: "Scoring settings saved. If values changed, run Recompute scores.",
        durationMs: 6000,
        dismissible: true,
      });
      onSaved?.();
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

  return (
    <Card>
      <Stack>
        <Muted>
          Points, upsets, tiebreaks, and bonuses. Changing scoring after matches exist requires a
          recompute.
        </Muted>

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
                members={members}
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
                  competitions={(league.pools ?? [])
                    .filter((p) => p.competition_code)
                    .map((p) => ({
                      competition_code: p.competition_code as string,
                      season_year: p.season_year ?? new Date().getFullYear(),
                    }))}
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
