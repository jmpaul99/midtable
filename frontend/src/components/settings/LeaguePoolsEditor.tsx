"use client";

import { Checkbox, Input, Label } from "@/components/ui/Field";
import { EditorSection, RowItem, RowList } from "./chrome";

export type LeaguePoolEdit = {
  id: string;
  key: string;
  label: string;
  sort_order: number;
  slot_count: number;
  scores_match_results: boolean;
  team_count?: number;
};

export function LeaguePoolsEditor({
  value,
  onChange,
  managerCapacity,
}: {
  value: LeaguePoolEdit[];
  onChange: (next: LeaguePoolEdit[]) => void;
  /** Required manager count used for club capacity checks. */
  managerCapacity: number;
}) {
  function update(index: number, patch: Partial<LeaguePoolEdit>) {
    onChange(value.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  const capacity = Math.max(1, managerCapacity || 1);

  return (
    <EditorSection
      title="Competitions"
      description="Each competition (e.g. Premier League, Championship) has its own roster slots, display order, and week-to-week scoring toggle."
    >
      {value.length === 0 ? (
        <p className="text-sm text-muted">No competitions configured for this league.</p>
      ) : (
        <RowList>
          {[...value]
            .map((p, index) => ({ p, index }))
            .sort(
              (a, b) =>
                a.p.sort_order - b.p.sort_order || a.p.label.localeCompare(b.p.label),
            )
            .map(({ p, index }) => {
              const slots = Number(p.slot_count) || 0;
              const teams = p.team_count ?? 0;
              const needed = slots * capacity;
              const overCapacity = teams > 0 && needed > teams;
              const maxSlots =
                teams > 0 ? Math.max(1, Math.floor(teams / capacity)) : undefined;

              return (
                <RowItem key={p.id}>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    <Label>
                      Label
                      <Input
                        value={p.label}
                        onChange={(e) => update(index, { label: e.target.value })}
                      />
                    </Label>
                    <Label>
                      Key
                      <Input value={p.key} disabled readOnly />
                    </Label>
                    <Label>
                      Display order
                      <Input
                        type="number"
                        min={0}
                        value={p.sort_order}
                        onChange={(e) =>
                          update(index, { sort_order: Number(e.target.value) })
                        }
                      />
                    </Label>
                    <Label>
                      Roster slots
                      <Input
                        type="number"
                        min={1}
                        max={maxSlots}
                        value={p.slot_count}
                        onChange={(e) =>
                          update(index, { slot_count: Number(e.target.value) })
                        }
                      />
                    </Label>
                  </div>

                  <p
                    className={
                      overCapacity
                        ? "mt-2 text-xs font-semibold text-danger"
                        : "mt-2 text-xs text-muted"
                    }
                  >
                    {slots} slots × {capacity} managers = {needed} clubs needed
                    {teams > 0
                      ? ` · ${teams} loaded${maxSlots != null ? ` · max ${maxSlots} slots` : ""}`
                      : " · load clubs to validate capacity"}
                    {overCapacity
                      ? ". Too many slots for the clubs available."
                      : "."}
                  </p>

                  <label className="mt-3 flex items-start gap-2 text-sm font-semibold text-muted">
                    <Checkbox
                      className="mt-0.5"
                      checked={p.scores_match_results}
                      onChange={(e) =>
                        update(index, { scores_match_results: e.target.checked })
                      }
                    />
                    <span>
                      Score week-to-week match results
                      <span className="mt-0.5 block text-xs font-normal">
                        When on, fixtures sync and W/D/L points count toward the leaderboard. When
                        off, clubs stay on rosters for season bonuses only.
                      </span>
                    </span>
                  </label>
                </RowItem>
              );
            })}
        </RowList>
      )}
    </EditorSection>
  );
}
