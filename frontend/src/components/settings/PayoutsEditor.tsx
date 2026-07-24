"use client";

import { Input, Label } from "@/components/ui/Field";
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
}: {
  value: PayoutRow[];
  onChange: (next: PayoutRow[]) => void;
}) {
  function update(index: number, patch: Partial<PayoutRow>) {
    onChange(value.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  return (
    <EditorSection
      title="Payouts"
      description="Cash prizes by phase and finishing position. Use phase key season for the full season."
    >
      {value.length > 0 && (
        <RowList>
          {value.map((p, index) => (
            <RowItem key={index}>
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Label>
                    Label
                    <Input
                      value={p.label}
                      onChange={(e) => update(index, { label: e.target.value })}
                      placeholder="Season 1st"
                    />
                  </Label>
                  <Label>
                    Phase key
                    <Input
                      value={p.phase}
                      onChange={(e) => update(index, { phase: e.target.value })}
                      placeholder="season"
                    />
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
