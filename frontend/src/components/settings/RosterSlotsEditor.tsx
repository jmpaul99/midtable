"use client";

import { Input, Label, Select } from "@/components/ui/Field";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import { humanizeKey, type RosterSlot } from "./types";

const blankSlot = (poolKey = ""): RosterSlot => ({
  pool_key: poolKey,
  count: 1,
  label: "",
});

export function RosterSlotsEditor({
  value,
  onChange,
  poolOptions,
}: {
  value: RosterSlot[];
  onChange: (next: RosterSlot[]) => void;
  /** Competition key → friendly name from pool definitions. */
  poolOptions?: Array<{ value: string; label: string }>;
}) {
  function update(index: number, patch: Partial<RosterSlot>) {
    onChange(value.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  const pools = [...(poolOptions || [])].filter((p) => p.value);
  const known = new Set(pools.map((p) => p.value));
  for (const row of value) {
    if (row.pool_key && !known.has(row.pool_key)) {
      pools.push({ value: row.pool_key, label: humanizeKey(row.pool_key) });
      known.add(row.pool_key);
    }
  }

  return (
    <EditorSection
      title="Roster slots"
      description="How many clubs each manager drafts from each competition in the shared draft."
    >
      {value.length > 0 && (
        <RowList>
          {value.map((r, index) => (
            <RowItem key={index}>
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_5rem_minmax(0,1fr)]">
                  <Label>
                    Competition
                    {pools.length > 0 ? (
                      <Select
                        value={r.pool_key}
                        onChange={(e) => {
                          const pool_key = e.target.value;
                          const opt = pools.find((p) => p.value === pool_key);
                          update(index, {
                            pool_key,
                            label: r.label.trim() ? r.label : opt?.label || "",
                          });
                        }}
                        required
                      >
                        <option value="">Select competition…</option>
                        {pools.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <Input
                        value={r.pool_key}
                        onChange={(e) => update(index, { pool_key: e.target.value })}
                        required
                      />
                    )}
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
                    Name
                    <Input
                      value={r.label}
                      onChange={(e) => update(index, { label: e.target.value })}
                      required
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
        label="Add roster slot"
        onClick={() =>
          onChange([
            ...value,
            blankSlot(pools[0]?.value || ""),
          ])
        }
      />
    </EditorSection>
  );
}
