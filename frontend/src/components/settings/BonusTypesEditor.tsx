"use client";

import { Input, Label } from "@/components/ui/Field";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import { slugifyKey, uniqueKey, type BonusTypeDef } from "./types";

function blankBonus(sortOrder: number, existingKeys: string[]): BonusTypeDef {
  return {
    key: uniqueKey("bonus", existingKeys, undefined, "bonus"),
    label: "",
    default_points: 0,
    sort_order: sortOrder,
  };
}

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

  function updateName(index: number, label: string) {
    const current = value[index];
    if (!current) return;
    const patch: Partial<BonusTypeDef> = { label };
    const hadName = Boolean((current.label ?? "").trim());
    const key = (current.key ?? "").trim();
    const placeholderKey = !key || /^bonus(_\d+)?$/.test(key);
    if (!hadName && label.trim() && placeholderKey) {
      patch.key = uniqueKey(
        slugifyKey(label) || "bonus",
        value.map((b) => b.key),
        index,
        "bonus",
      );
    }
    update(index, patch);
  }

  return (
    <EditorSection
      title="Bonus types"
      description="Season-end / manual bonus categories seeded onto new leagues from this template."
    >
      {value.length > 0 && (
        <RowList>
          {value.map((b, index) => (
            <RowItem key={b.key || index}>
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_6.5rem_5.5rem]">
                  <Label>
                    Name
                    <Input
                      value={b.label ?? ""}
                      onChange={(e) => updateName(index, e.target.value)}
                      required
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
        onClick={() =>
          onChange([
            ...value,
            blankBonus(
              value.length + 1,
              value.map((b) => b.key),
            ),
          ])
        }
      />
    </EditorSection>
  );
}
