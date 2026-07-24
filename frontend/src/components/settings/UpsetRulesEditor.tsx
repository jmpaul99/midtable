"use client";

import { Checkbox, Input, Label, Select } from "@/components/ui/Field";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import type { UpsetRules, UpsetThreshold } from "./types";

const blankThreshold = (): UpsetThreshold => ({
  key: "minor_upset",
  result: "win",
  min_gap: 5,
  max_gap: 9,
  points: 1,
});

export function UpsetRulesEditor({
  value,
  onChange,
}: {
  value: UpsetRules;
  onChange: (next: UpsetRules) => void;
}) {
  const fixed = value.rank_source === "fixed_ranking_at_event_start";

  function updateThreshold(index: number, patch: Partial<UpsetThreshold>) {
    onChange({
      ...value,
      thresholds: value.thresholds.map((t, i) => (i === index ? { ...t, ...patch } : t)),
    });
  }

  function removeThreshold(index: number) {
    onChange({
      ...value,
      thresholds: value.thresholds.filter((_, i) => i !== index),
    });
  }

  return (
    <EditorSection
      title="Upset rules"
      description="Bonus points when a lower-ranked team beats (or draws) a higher-ranked one."
    >
      <label className="flex items-center gap-2 text-sm font-semibold text-muted">
        <Checkbox
          checked={value.enabled}
          onChange={(e) => onChange({ ...value, enabled: e.target.checked })}
        />
        Upsets enabled
      </label>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Label>
          Rank source
          <Select
            value={value.rank_source}
            onChange={(e) =>
              onChange({
                ...value,
                rank_source: e.target.value,
                ranking_list_key:
                  e.target.value === "fixed_ranking_at_event_start"
                    ? value.ranking_list_key || "fifa_men"
                    : null,
              })
            }
          >
            <option value="league_table_at_kickoff">League table at kickoff</option>
            <option value="fixed_ranking_at_event_start">Fixed ranking list (e.g. FIFA)</option>
          </Select>
        </Label>
        <Label>
          Min games played
          <Input
            type="number"
            min={0}
            value={value.min_played}
            onChange={(e) => onChange({ ...value, min_played: Number(e.target.value) })}
          />
        </Label>
      </div>

      {fixed && (
        <Label>
          Ranking list key
          <Input
            value={value.ranking_list_key || ""}
            onChange={(e) => onChange({ ...value, ranking_list_key: e.target.value || null })}
            placeholder="fifa_men"
          />
        </Label>
      )}

      {value.thresholds.length > 0 && (
        <RowList>
          {value.thresholds.map((t, index) => (
            <RowItem key={index}>
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  <Label>
                    Key
                    <Input
                      value={t.key}
                      onChange={(e) => updateThreshold(index, { key: e.target.value })}
                    />
                  </Label>
                  <Label>
                    Result
                    <Select
                      value={t.result}
                      onChange={(e) =>
                        updateThreshold(index, {
                          result: e.target.value as UpsetThreshold["result"],
                        })
                      }
                    >
                      <option value="win">Win</option>
                      <option value="draw">Draw</option>
                      <option value="loss">Loss</option>
                    </Select>
                  </Label>
                  <Label>
                    Points
                    <Input
                      type="number"
                      step="0.5"
                      value={t.points}
                      onChange={(e) => updateThreshold(index, { points: Number(e.target.value) })}
                    />
                  </Label>
                  <Label>
                    Min gap
                    <Input
                      type="number"
                      min={0}
                      value={t.min_gap}
                      onChange={(e) => updateThreshold(index, { min_gap: Number(e.target.value) })}
                    />
                  </Label>
                  <Label>
                    Max gap
                    <Input
                      type="number"
                      min={0}
                      value={t.max_gap ?? ""}
                      placeholder="∞"
                      onChange={(e) =>
                        updateThreshold(index, {
                          max_gap: e.target.value === "" ? null : Number(e.target.value),
                        })
                      }
                    />
                  </Label>
                </div>
                <div className="flex justify-end">
                  <RemoveButton onClick={() => removeThreshold(index)} />
                </div>
              </div>
            </RowItem>
          ))}
        </RowList>
      )}

      <AddRowButton
        label="Add threshold"
        onClick={() => onChange({ ...value, thresholds: [...value.thresholds, blankThreshold()] })}
      />
    </EditorSection>
  );
}
