"use client";

import { Input, Label } from "@/components/ui/Field";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import type { BonusTypeDef } from "./types";

const blankBonus = (sortOrder: number): BonusTypeDef => ({
  key: "",
  label: "",
  default_points: 0,
  sort_order: sortOrder,
});

export function BonusTypesEditor({
  value,
  onChange,
}: {
  value: BonusTypeDef[];
  onChange: (next: BonusTypeDef[]) => void;
}) {
  function update(index: number, patch: Partial<BonusTypeDef>) {
    onChange(value.map((b, i) => (i === index ? { ...b, ...patch } : b)));
  }

  return (
    <EditorSection
      title="Bonus types"
      description="Season-end / manual bonus categories seeded onto new leagues from this template."
    >
      {value.length > 0 && (
        <RowList>
          {value.map((b, index) => (
            <RowItem key={index}>
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Label>
                    Key
                    <Input
                      value={b.key}
                      onChange={(e) => update(index, { key: e.target.value })}
                      placeholder="cl"
                    />
                  </Label>
                  <Label>
                    Label
                    <Input
                      value={b.label}
                      onChange={(e) => update(index, { label: e.target.value })}
                      placeholder="Champions League Qualification"
                    />
                  </Label>
                  <Label>
                    Default points
                    <Input
                      type="number"
                      step="0.5"
                      value={b.default_points}
                      onChange={(e) => update(index, { default_points: Number(e.target.value) })}
                    />
                  </Label>
                  <Label>
                    Sort order
                    <Input
                      type="number"
                      value={b.sort_order}
                      onChange={(e) => update(index, { sort_order: Number(e.target.value) })}
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
      <AddRowButton
        label="Add bonus type"
        onClick={() => onChange([...value, blankBonus(value.length + 1)])}
      />
    </EditorSection>
  );
}
