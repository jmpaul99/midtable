"use client";

import { useCallback, useRef } from "react";
import { Autocomplete } from "@/components/ui/Autocomplete";
import { formatMatchOptionLabel } from "@/lib/format";
import { fetchMatchLogPage } from "@/lib/matchLog";
import type { MatchLogRow, UUID } from "@/lib/types";

const PAGE_SIZE = 50;

export function MatchAutocomplete({
  leagueId,
  value,
  selectedMatch,
  onChange,
  required = false,
  disabled = false,
  placeholder = "Search matches…",
  id,
  className,
}: {
  leagueId: UUID;
  value: string;
  /** Cached selected row so the label stays visible after search results change. */
  selectedMatch: MatchLogRow | null;
  onChange: (matchId: string, match: MatchLogRow | null) => void;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  id?: string;
  className?: string;
}) {
  const cacheRef = useRef(new Map<string, MatchLogRow>());
  if (selectedMatch) {
    cacheRef.current.set(selectedMatch.id, selectedMatch);
  }

  const loadOptions = useCallback(
    async (query: string, { offset }: { offset: number }) => {
      const page = await fetchMatchLogPage(leagueId, {
        limit: PAGE_SIZE,
        offset,
        q: query || undefined,
      });
      for (const row of page.items) {
        cacheRef.current.set(row.id, row);
      }
      return {
        items: page.items.map((row) => ({
          value: row.id,
          label: formatMatchOptionLabel(row),
        })),
        hasMore: page.has_more,
      };
    },
    [leagueId],
  );

  return (
    <Autocomplete
      value={value}
      onChange={(next) => {
        if (!next) {
          onChange("", null);
          return;
        }
        onChange(next, cacheRef.current.get(next) ?? null);
      }}
      loadOptions={loadOptions}
      selectedLabel={selectedMatch ? formatMatchOptionLabel(selectedMatch) : ""}
      disabled={disabled}
      required={required}
      placeholder={placeholder}
      emptyMessage="No matches found."
      idleEmptyMessage="No matches synced yet."
      loadingEmptyMessage="Searching…"
      loadMoreLabel="Show more matches"
      id={id}
      className={className}
    />
  );
}
