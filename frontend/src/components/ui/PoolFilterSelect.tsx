"use client";

import { humanizeKey } from "@/components/settings/types";
import { Select } from "@/components/ui/Field";

type PoolOption = {
  id: string;
  label?: string | null;
  key?: string | null;
};

function poolOptionLabel(p: PoolOption): string {
  const label = (p.label || "").trim();
  if (label) return label;
  if (p.key) return humanizeKey(p.key);
  return p.id;
}

/** Competition/pool filter; empty string means all competitions. */
export function PoolFilterSelect({
  pools,
  value,
  onChange,
  id,
  name,
  className,
  allLabel = "All competitions",
  "aria-label": ariaLabel = "Competition",
}: {
  pools: PoolOption[];
  value: string;
  onChange: (value: string) => void;
  id?: string;
  name?: string;
  className?: string;
  allLabel?: string;
  "aria-label"?: string;
}) {
  return (
    <Select
      id={id}
      name={name}
      aria-label={ariaLabel}
      className={className}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{allLabel}</option>
      {pools.map((p) => (
        <option key={p.id} value={p.id}>
          {poolOptionLabel(p)}
        </option>
      ))}
    </Select>
  );
}
