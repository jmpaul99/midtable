"use client";

import type { ReactNode } from "react";
import { Checkbox, Input, Label } from "@/components/ui/Field";
import {
  AVAILABLE_COMPETITIONS,
  competitionDisplayLabel,
  defaultFootballSeasonYear,
  findAvailableCompetition,
} from "@/lib/availableCompetitions";
import { cn } from "@/lib/cn";
import {
  normalizeRosterClubOrder,
  type RosterClubOrder,
} from "@/lib/rosterClubOrder";
import { CompetitionAutocomplete } from "./CompetitionAutocomplete";
import { SeasonYearField } from "./SeasonYearField";
import {
  AddRowButton,
  EditorSection,
  RemoveButton,
  ReorderButtons,
  RowItem,
  RowList,
} from "./chrome";

export type LeaguePoolEdit = {
  /** Persisted public id, or a client-only temp id for unsaved rows. */
  id: string;
  isNew?: boolean;
  key: string;
  label: string;
  sort_order: number;
  slot_count: number;
  scores_match_results: boolean;
  competition_code: string;
  season_year: number;
  provider: string;
  team_count?: number;
};

function blankPool(sortOrder: number): LeaguePoolEdit {
  return {
    id: `temp-${crypto.randomUUID()}`,
    isNew: true,
    key: "",
    label: "",
    sort_order: sortOrder,
    slot_count: 1,
    scores_match_results: true,
    competition_code: "",
    season_year: defaultFootballSeasonYear(),
    provider: "football-data.org",
    team_count: 0,
  };
}

function sortPools(pools: LeaguePoolEdit[]): LeaguePoolEdit[] {
  return [...pools].sort(
    (a, b) => a.sort_order - b.sort_order || a.label.localeCompare(b.label),
  );
}

function withRenumberedOrder(pools: LeaguePoolEdit[]): LeaguePoolEdit[] {
  return pools.map((p, i) => ({ ...p, sort_order: i + 1 }));
}

export function LeaguePoolsEditor({
  value,
  onChange,
  managerCapacity,
  structureEditable = true,
  trailingAction,
  rosterClubOrder = "draft",
  onRosterClubOrderChange,
  showHeading = true,
}: {
  value: LeaguePoolEdit[];
  onChange: (next: LeaguePoolEdit[]) => void;
  /** Manager count for club capacity checks. When omitted, capacity hints are hidden. */
  managerCapacity?: number;
  /** When true, allow add/remove and competition selection. Defaults to true. */
  structureEditable?: boolean;
  /** Shown on the right of the footer row (e.g. Save), opposite Add. */
  trailingAction?: ReactNode;
  rosterClubOrder?: RosterClubOrder;
  onRosterClubOrderChange?: (next: RosterClubOrder) => void;
  /** When false, omit the section title (e.g. wizard already shows the step name). */
  showHeading?: boolean;
}) {
  const ordered = sortPools(value);
  const showCapacity = managerCapacity != null;

  function updateById(id: string, patch: Partial<LeaguePoolEdit>) {
    onChange(value.map((p) => (p.id === id ? { ...p, ...patch } : p)));
  }

  function selectCompetition(id: string, code: string) {
    const entry = findAvailableCompetition(code);
    if (!entry) {
      updateById(id, { competition_code: "", key: "", label: "" });
      return;
    }
    updateById(id, {
      competition_code: entry.code,
      key: entry.key,
      label: entry.label,
    });
  }

  function reorder(from: number, to: number) {
    if (from === to || from < 0 || to < 0 || from >= ordered.length || to >= ordered.length) {
      return;
    }
    const next = [...ordered];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(withRenumberedOrder(next));
  }

  const capacity = Math.max(1, managerCapacity || 1);
  const usedCodes = new Set(
    value.map((p) => p.competition_code?.trim().toUpperCase()).filter(Boolean),
  );
  const showRosterOrder = Boolean(onRosterClubOrderChange) && value.length > 1;

  return (
    <EditorSection
      title={showHeading ? "Competitions" : undefined}
        description={
          showRosterOrder
          ? "These are the real-world leagues managers draft clubs from (e.g. Premier League, Championship). One shared draft covers every competition you add. The arrows set the pre-draft order shown on rosters. After the draft, rosters default to draft order — change that below if you want."
          : "Real-world competitions managers draft from in one shared draft (e.g. Premier League + Championship). The arrows set the pre-draft order shown on rosters (first in the list appears first)."
        }
    >
      {!structureEditable && (
        <p className="text-sm text-muted">
          Competition structure (add/remove, season, and slots) is locked after the draft opens.
        </p>
      )}

      {showRosterOrder && (
        <div className="flex max-w-lg flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
          <p className="shrink-0 text-xs font-semibold text-muted sm:w-36">
            Roster order after draft
          </p>
          <div className="min-w-0 flex-1">
            <div
              className="inline-flex w-full gap-0.5 rounded-lg bg-surface-2 p-0.5 sm:w-auto"
              role="radiogroup"
              aria-label="Roster order after draft"
            >
              {(
                [
                  { id: "draft", label: "Draft order" },
                  { id: "competition", label: "Competition order" },
                ] as const
              ).map((opt) => {
                const selected = normalizeRosterClubOrder(rosterClubOrder) === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => onRosterClubOrderChange?.(opt.id)}
                    className={cn(
                      "min-h-8 flex-1 rounded-md px-2.5 py-1 text-xs font-bold transition sm:flex-none",
                      selected ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink",
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
            <p className="mt-1 text-[0.65rem] leading-snug text-muted">
              Pre-draft always uses competition order.
            </p>
          </div>
        </div>
      )}

      {ordered.length === 0 ? (
        <p className="text-sm text-muted">
          {structureEditable
            ? showCapacity
              ? "No competitions yet. Add at least one before the draft opens."
              : "No competitions yet. Add at least one."
            : "No competitions configured for this league."}
        </p>
      ) : (
        <RowList>
          {ordered.map((p, sortedIndex) => {
            const slots = Number(p.slot_count) || 0;
            const teams = p.team_count ?? 0;
            const needed = slots * capacity;
            const overCapacity = showCapacity && teams > 0 && needed > teams;
            const maxSlots =
              showCapacity && teams > 0
                ? Math.max(1, Math.floor(teams / capacity))
                : undefined;
            const options = AVAILABLE_COMPETITIONS.filter(
              (c) =>
                c.code === p.competition_code?.toUpperCase() || !usedCodes.has(c.code),
            );
            const displayName = competitionDisplayLabel(p.competition_code, p.label);

            return (
              <RowItem key={p.id} className="p-2.5 sm:p-3">
                <div className="flex items-start gap-2">
                  <ReorderButtons
                    index={sortedIndex}
                    total={ordered.length}
                    onMove={reorder}
                    itemLabel="competition"
                  />
                  <div className="min-w-0 flex-1 space-y-2">
                    <div
                      className={cn(
                        "grid items-start gap-2",
                        structureEditable
                          ? "grid-cols-[minmax(0,1fr)_4.5rem_5.5rem_auto]"
                          : "grid-cols-[minmax(0,1fr)_4.5rem_5.5rem]",
                      )}
                    >
                      <Label className="min-w-0 gap-1">
                        Competition
                        {structureEditable ? (
                          <CompetitionAutocomplete
                            value={p.competition_code || ""}
                            onChange={(code) => selectCompetition(p.id, code)}
                            options={options}
                            required
                            className="min-h-10 rounded-lg px-2.5 py-2 text-sm"
                          />
                        ) : (
                          <Input
                            value={displayName || p.key}
                            disabled
                            readOnly
                            className="min-h-10 rounded-lg px-2.5 py-2 text-sm"
                          />
                        )}
                      </Label>
                      <Label className="gap-1">
                        Slots
                        <Input
                          type="number"
                          min={1}
                          max={maxSlots}
                          value={p.slot_count}
                          disabled={!structureEditable}
                          onChange={(e) =>
                            updateById(p.id, { slot_count: Number(e.target.value) })
                          }
                          className="min-h-10 rounded-lg px-2.5 py-2 text-sm"
                        />
                        {showCapacity && structureEditable && (
                          <span
                            className={cn(
                              "text-[0.65rem] font-normal leading-snug",
                              overCapacity ? "font-semibold text-danger" : "text-muted",
                            )}
                          >
                            {teams > 0
                              ? `${teams} teams${maxSlots != null ? ` · max ${maxSlots}` : ""}`
                              : "No teams yet"}
                            {overCapacity ? " — too many slots" : ""}
                          </span>
                        )}
                      </Label>
                      <SeasonYearField
                        value={p.season_year}
                        onChange={(year) => updateById(p.id, { season_year: year })}
                        disabled={!structureEditable}
                        required={structureEditable}
                        compact
                      />
                      {structureEditable && (
                        <div className="pt-[1.375rem]">
                          <RemoveButton
                            onClick={() =>
                              onChange(
                                withRenumberedOrder(
                                  ordered.filter((row) => row.id !== p.id),
                                ),
                              )
                            }
                          />
                        </div>
                      )}
                    </div>

                    <label className="flex items-start gap-1.5 text-xs font-semibold text-muted">
                      <Checkbox
                        className="mt-0.5 size-4"
                        checked={p.scores_match_results}
                        onChange={(e) =>
                          updateById(p.id, { scores_match_results: e.target.checked })
                        }
                      />
                      <span>
                        Score match results
                        <span className="mt-0.5 block text-[0.7rem] font-normal leading-snug">
                          When on, fixtures sync and W/D/L points count toward the leaderboard. When
                          off, clubs stay on rosters for season bonuses only.
                        </span>
                      </span>
                    </label>
                  </div>
                </div>
              </RowItem>
            );
          })}
        </RowList>
      )}

      {(structureEditable || trailingAction) && (
        <div className="flex items-center justify-between gap-3">
          {structureEditable ? (
            <AddRowButton
              label="Add competition"
              onClick={() =>
                onChange([
                  ...withRenumberedOrder(ordered),
                  blankPool(ordered.length + 1),
                ])
              }
            />
          ) : (
            <span />
          )}
          {trailingAction}
        </div>
      )}
    </EditorSection>
  );
}
