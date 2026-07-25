"use client";

import { Checkbox, Input, Label } from "@/components/ui/Field";
import {
  AVAILABLE_COMPETITIONS,
  defaultFootballSeasonYear,
  findAvailableCompetition,
} from "@/lib/availableCompetitions";
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
import type { PoolDefinition } from "./types";

const blankPool = (): PoolDefinition => ({
  key: "",
  label: "",
  scores_match_results: true,
  slot_count: 1,
  sort_order: 1,
  provider: "football-data.org",
  competition_code: "",
  season_year: defaultFootballSeasonYear(),
  tie_break_order: ["points", "gd", "gf", "name"],
});

function sortPools(pools: PoolDefinition[]): Array<{ p: PoolDefinition; index: number }> {
  return pools
    .map((p, index) => ({ p, index }))
    .sort(
      (a, b) =>
        (a.p.sort_order || 0) - (b.p.sort_order || 0) ||
        (a.p.label || "").localeCompare(b.p.label || ""),
    );
}

export function PoolDefinitionsEditor({
  value,
  onChange,
}: {
  value: PoolDefinition[];
  onChange: (next: PoolDefinition[]) => void;
}) {
  const ordered = sortPools(value);

  function update(index: number, patch: Partial<PoolDefinition>) {
    onChange(value.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  function selectCompetition(index: number, code: string) {
    const entry = findAvailableCompetition(code);
    if (!entry) {
      update(index, { competition_code: "", key: "", label: "" });
      return;
    }
    update(index, {
      competition_code: entry.code,
      key: entry.key,
      label: entry.label,
    });
  }

  function reorder(fromSorted: number, toSorted: number) {
    if (
      fromSorted === toSorted ||
      fromSorted < 0 ||
      toSorted < 0 ||
      fromSorted >= ordered.length ||
      toSorted >= ordered.length
    ) {
      return;
    }
    const next = ordered.map(({ p }) => ({ ...p }));
    const [item] = next.splice(fromSorted, 1);
    next.splice(toSorted, 0, item);
    onChange(next.map((p, i) => ({ ...p, sort_order: i + 1 })));
  }

  const usedCodes = new Set(
    value.map((p) => p.competition_code?.trim().toUpperCase()).filter(Boolean),
  );

  return (
    <EditorSection
      title="Competitions"
      description="Real-world competitions managers draft from (e.g. Premier League + Championship). The arrows set the pre-draft order shown on rosters (first in the list appears first)."
    >
      {ordered.length > 0 && (
        <RowList>
          {ordered.map(({ p, index }, sortedIndex) => {
            const options = AVAILABLE_COMPETITIONS.filter(
              (c) =>
                c.code === p.competition_code?.toUpperCase() || !usedCodes.has(c.code),
            );
            return (
              <RowItem key={index}>
                <div className="flex items-start gap-2">
                  <ReorderButtons
                    index={sortedIndex}
                    total={ordered.length}
                    onMove={reorder}
                    itemLabel="competition"
                  />
                  <div className="flex min-w-0 flex-1 flex-col gap-2">
                    <div className="grid grid-cols-1 gap-2 md:grid-cols-[minmax(0,2.2fr)_minmax(0,0.75fr)_minmax(0,0.9fr)] md:items-start">
                      <Label>
                        Competition
                        <CompetitionAutocomplete
                          value={p.competition_code || ""}
                          onChange={(code) => selectCompetition(index, code)}
                          options={options}
                          required
                        />
                      </Label>
                      <Label>
                        Roster slots
                        <Input
                          type="number"
                          min={1}
                          value={p.slot_count}
                          onChange={(e) =>
                            update(index, { slot_count: Number(e.target.value) })
                          }
                        />
                      </Label>
                      <SeasonYearField
                        value={p.season_year}
                        onChange={(year) => update(index, { season_year: year })}
                        required
                      />
                    </div>
                    <label className="flex items-start gap-2 text-sm font-semibold text-muted">
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
                          Off = roster/bonus competition only (e.g. Championship promotion). On =
                          sync fixtures and count W/D/L points.
                        </span>
                      </span>
                    </label>
                    <div className="flex justify-end">
                      <RemoveButton
                        onClick={() => {
                          const next = ordered
                            .filter((_, i) => i !== sortedIndex)
                            .map(({ p: row }, i) => ({ ...row, sort_order: i + 1 }));
                          onChange(next);
                        }}
                      />
                    </div>
                  </div>
                </div>
              </RowItem>
            );
          })}
        </RowList>
      )}
      <AddRowButton
        label="Add competition"
        onClick={() =>
          onChange([
            ...ordered.map(({ p }, i) => ({ ...p, sort_order: i + 1 })),
            {
              ...blankPool(),
              sort_order: ordered.length + 1,
            },
          ])
        }
      />
    </EditorSection>
  );
}
