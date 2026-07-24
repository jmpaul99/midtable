"use client";

import { Checkbox, Input, Label } from "@/components/ui/Field";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import type { PoolDefinition } from "./types";

const blankPool = (): PoolDefinition => ({
  key: "",
  label: "",
  scores_match_results: true,
  slot_count: 1,
  sort_order: 1,
  provider: "football-data.org",
  competition_code: "",
  season_year: new Date().getFullYear(),
  tie_break_order: ["points", "gd", "gf", "name"],
});

export function PoolDefinitionsEditor({
  value,
  onChange,
}: {
  value: PoolDefinition[];
  onChange: (next: PoolDefinition[]) => void;
}) {
  function update(index: number, patch: Partial<PoolDefinition>) {
    onChange(value.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  return (
    <EditorSection
      title="Competitions"
      description="Real-world competitions managers draft from (e.g. Premier League + Championship). Lower display order appears first on rosters. Use “Score week-to-week match results” for weekly points vs bonus-only competitions."
    >
      {value.length > 0 && (
        <RowList>
          {value.map((p, index) => (
            <RowItem key={index}>
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Label>
                    Key
                    <Input
                      value={p.key}
                      onChange={(e) => update(index, { key: e.target.value })}
                      placeholder="premier_league"
                    />
                  </Label>
                  <Label>
                    Label
                    <Input
                      value={p.label}
                      onChange={(e) => update(index, { label: e.target.value })}
                      placeholder="Premier League"
                    />
                  </Label>
                  <Label>
                    Competition code
                    <Input
                      value={p.competition_code}
                      onChange={(e) => update(index, { competition_code: e.target.value })}
                      placeholder="PL"
                    />
                  </Label>
                  <Label>
                    Season year
                    <Input
                      type="number"
                      value={p.season_year}
                      onChange={(e) => update(index, { season_year: Number(e.target.value) })}
                    />
                  </Label>
                  <Label>
                    Roster slots
                    <Input
                      type="number"
                      min={1}
                      value={p.slot_count}
                      onChange={(e) => update(index, { slot_count: Number(e.target.value) })}
                    />
                  </Label>
                  <Label>
                    Display order
                    <Input
                      type="number"
                      min={1}
                      value={p.sort_order}
                      onChange={(e) => update(index, { sort_order: Number(e.target.value) })}
                      placeholder="1"
                    />
                  </Label>
                  <Label>
                    Provider
                    <Input
                      value={p.provider}
                      onChange={(e) => update(index, { provider: e.target.value })}
                    />
                  </Label>
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
                      Off = roster/bonus competition only (e.g. Championship promotion). On = sync fixtures
                      and count W/D/L points.
                    </span>
                  </span>
                </label>
                <div className="flex justify-end">
                  <RemoveButton onClick={() => onChange(value.filter((_, i) => i !== index))} />
                </div>
              </div>
            </RowItem>
          ))}
        </RowList>
      )}
      <AddRowButton
        label="Add competition"
        onClick={() =>
          onChange([
            ...value,
            {
              ...blankPool(),
              sort_order: value.reduce((max, p) => Math.max(max, p.sort_order || 0), 0) + 1,
            },
          ])
        }
      />
    </EditorSection>
  );
}
