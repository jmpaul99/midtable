"use client";

import { Input, Label } from "@/components/ui/Field";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import type { RosterSlot } from "./types";

const blankSlot = (): RosterSlot => ({
  pool_key: "",
  count: 1,
  label: "",
});

export function RosterSlotsEditor({
  value,
  onChange,
}: {
  value: RosterSlot[];
  onChange: (next: RosterSlot[]) => void;
}) {
  function update(index: number, patch: Partial<RosterSlot>) {
    onChange(value.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  return (
    <EditorSection
      title="Roster slots"
      description="How many teams each manager drafts from each competition. Key must match a competition definition."
    >
      {value.length > 0 && (
        <RowList>
          {value.map((r, index) => (
            <RowItem key={index}>
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  <Label>
                    Competition key
                    <Input
                      value={r.pool_key}
                      onChange={(e) => update(index, { pool_key: e.target.value })}
                      placeholder="premier_league"
                    />
                  </Label>
                  <Label>
                    Count
                    <Input
                      type="number"
                      min={1}
                      value={r.count}
                      onChange={(e) => update(index, { count: Number(e.target.value) })}
                    />
                  </Label>
                  <Label>
                    Label
                    <Input
                      value={r.label}
                      onChange={(e) => update(index, { label: e.target.value })}
                      placeholder="Premier League team"
                    />
                  </Label>
                </div>
                <div className="flex justify-end">
                  <RemoveButton onClick={() => onChange(value.filter((_, i) => i !== index))} />
                </div>
              </div>
            </RowItem>
          ))}
        </RowList>
      )}
      <AddRowButton label="Add roster slot" onClick={() => onChange([...value, blankSlot()])} />
    </EditorSection>
  );
}
