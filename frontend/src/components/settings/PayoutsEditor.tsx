"use client";

import { Input, Label, Select } from "@/components/ui/Field";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import type { PayoutRow } from "./types";

const compactInput = "min-h-10 rounded-lg px-2.5 py-2 text-sm";

const blankPayout = (): PayoutRow => ({
  label: "",
  phase: "season",
  position: 1,
  amount: 0,
});

export function PayoutsEditor({
  value,
  onChange,
  phaseOptions,
}: {
  value: PayoutRow[];
  onChange: (next: PayoutRow[]) => void;
  /** Phase key → friendly name. Always includes Overall (`season`). */
  phaseOptions?: Array<{ value: string; label: string }>;
}) {
  function update(index: number, patch: Partial<PayoutRow>) {
    onChange(value.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  const phases = [
    { value: "season", label: "Overall" },
    ...(phaseOptions || []).filter((p) => p.value && p.value !== "season"),
  ];
  // Keep orphan phase keys selectable so existing payouts remain editable.
  const known = new Set(phases.map((p) => p.value));
  for (const row of value) {
    if (row.phase && !known.has(row.phase)) {
      phases.push({ value: row.phase, label: row.phase });
      known.add(row.phase);
    }
  }

  return (
    <EditorSection
      title="Payouts"
      description="Cash prizes by phase and finishing position."
    >
      {value.length > 0 && (
        <RowList>
          {value.map((p, index) => (
            <RowItem key={index} className="p-2.5 sm:p-3">
              <div className="flex min-w-0 flex-wrap items-end gap-2">
                <Label className="min-w-0 flex-1 basis-[10rem] gap-1">
                  Name
                  <Input
                    value={p.label}
                    onChange={(e) => update(index, { label: e.target.value })}
                    className={compactInput}
                    required
                  />
                </Label>
                <Label className="min-w-0 flex-1 basis-[8rem] gap-1 sm:max-w-[10rem]">
                  Phase
                  <Select
                    value={p.phase}
                    onChange={(e) => update(index, { phase: e.target.value })}
                    className={compactInput}
                  >
                    {phases.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </Select>
                </Label>
                <Label className="w-[4.5rem] shrink-0 gap-1">
                  Pos
                  <Input
                    type="number"
                    min={1}
                    value={p.position}
                    onChange={(e) => update(index, { position: Number(e.target.value) })}
                    className={compactInput}
                  />
                </Label>
                <Label className="w-[6rem] shrink-0 gap-1">
                  Amount
                  <Input
                    type="number"
                    step="0.01"
                    value={p.amount}
                    onChange={(e) => update(index, { amount: Number(e.target.value) })}
                    className={compactInput}
                  />
                </Label>
                <div className="flex shrink-0 pb-0.5">
                  <RemoveButton onClick={() => onChange(value.filter((_, i) => i !== index))} />
                </div>
              </div>
            </RowItem>
          ))}
        </RowList>
      )}
      <AddRowButton label="Add payout" onClick={() => onChange([...value, blankPayout()])} />
    </EditorSection>
  );
}
