"use client";

import { useMemo } from "react";
import { Autocomplete } from "@/components/ui/Autocomplete";
import {
  type AvailableCompetition,
  competitionDisplayLabel,
} from "@/lib/availableCompetitions";

export function CompetitionAutocomplete({
  value,
  onChange,
  options,
  disabled = false,
  required = false,
  placeholder = "Search competitions…",
  id,
  className,
}: {
  /** Selected competition code (e.g. PL). */
  value: string;
  onChange: (code: string) => void;
  /** Options available for this row (already excluding used codes). */
  options: AvailableCompetition[];
  disabled?: boolean;
  required?: boolean;
  placeholder?: string;
  id?: string;
  className?: string;
}) {
  const autocompleteOptions = useMemo(() => {
    const mapped = options.map((o) => ({
      value: o.code,
      label: o.label,
      keywords: [o.key],
    }));
    if (!value) return mapped;
    if (mapped.some((o) => o.value === value)) return mapped;
    const label = competitionDisplayLabel(value);
    return label ? [{ value, label }, ...mapped] : mapped;
  }, [options, value]);

  return (
    <Autocomplete
      value={value}
      onChange={onChange}
      options={autocompleteOptions}
      disabled={disabled}
      required={required}
      placeholder={placeholder}
      emptyMessage="No competitions match."
      id={id}
      className={className}
    />
  );
}
