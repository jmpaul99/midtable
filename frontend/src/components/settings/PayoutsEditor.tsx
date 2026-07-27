"use client";

import { Input, Label, Select } from "@/components/ui/Field";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import type { PayoutRow } from "./types";

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
            <RowItem key={index}>
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Label>
                    Name
                    <Input
                      value={p.label}
                      onChange={(e) => update(index, { label: e.target.value })}
                      required
                    />
                  </Label>
                  <Label>
                    Phase
                    <Select
                      value={p.phase}
                      onChange={(e) => update(index, { phase: e.target.value })}
                    >
                      {phases.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </Select>
                  </Label>
                  <Label>
                    Position
                    <Input
                      type="number"
                      min={1}
                      value={p.position}
                      onChange={(e) => update(index, { position: Number(e.target.value) })}
                    />
                  </Label>
                  <Label>
                    Amount
                    <Input
                      type="number"
                      step="0.01"
                      value={p.amount}
                      onChange={(e) => update(index, { amount: Number(e.target.value) })}
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
      <AddRowButton label="Add payout" onClick={() => onChange([...value, blankPayout()])} />
    </EditorSection>
  );
}
