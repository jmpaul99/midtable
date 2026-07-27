"use client";

import { useEffect, useId, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { MatchLogPage, MatchLogRow, UUID } from "@/lib/types";
import { Input } from "@/components/ui/Field";
import { cn } from "@/lib/cn";

function matchOptionLabel(m: MatchLogRow): string {
  const score =
    m.home_goals != null && m.away_goals != null
      ? ` ${m.home_goals}-${m.away_goals}`
      : "";
  const mw = m.scheduled_matchweek != null ? ` · MW${m.scheduled_matchweek}` : "";
  return `${m.home_team_name} vs ${m.away_team_name}${score}${mw}`;
}

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
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const selectedLabel = selectedMatch ? matchOptionLabel(selectedMatch) : "";
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(selectedLabel);
  const [options, setOptions] = useState<MatchLogRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    if (!open) setQuery(selectedLabel);
  }, [selectedLabel, open, value]);

  useEffect(() => {
    if (!open || disabled) return;
    const search =
      selectedLabel && query.trim().toLowerCase() === selectedLabel.toLowerCase()
        ? ""
        : query.trim();
    let cancelled = false;
    const handle = window.setTimeout(() => {
      setLoading(true);
      const qs = new URLSearchParams({
        section: "results",
        limit: "20",
        offset: "0",
      });
      if (search) qs.set("q", search);
      api<MatchLogPage>(`/leagues/${leagueId}/match-log?${qs}`)
        .then((page) => {
          if (!cancelled) setOptions(page.items);
        })
        .catch(() => {
          if (!cancelled) setOptions([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, search ? 250 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [open, query, selectedLabel, leagueId, disabled]);

  useEffect(() => {
    setActiveIndex(0);
  }, [options, open]);

  useEffect(() => {
    function onDocPointerDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setQuery(selectedLabel);
      }
    }
    document.addEventListener("mousedown", onDocPointerDown);
    return () => document.removeEventListener("mousedown", onDocPointerDown);
  }, [selectedLabel]);

  function pick(row: MatchLogRow) {
    onChange(row.id, row);
    setQuery(matchOptionLabel(row));
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (disabled) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) => Math.min(i + 1, Math.max(options.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (open && options[activeIndex]) {
        e.preventDefault();
        pick(options[activeIndex]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setQuery(selectedLabel);
    }
  }

  const emptyMessage = loading
    ? "Searching…"
    : query.trim()
      ? "No matches found."
      : "No finished matches yet.";

  return (
    <div ref={rootRef} className="relative">
      <Input
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={
          open && options[activeIndex] ? `${listId}-${options[activeIndex].id}` : undefined
        }
        autoComplete="off"
        disabled={disabled}
        required={required && !value}
        placeholder={placeholder}
        className={className}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          if (!e.target.value.trim() && value) {
            onChange("", null);
          }
        }}
        onFocus={(e) => {
          setOpen(true);
          setQuery(selectedLabel);
          e.currentTarget.select();
        }}
        onKeyDown={onKeyDown}
      />
      {open && !disabled && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto overscroll-contain rounded-xl border border-line bg-surface py-1 shadow-lg"
        >
          {options.length === 0 ? (
            <li className="px-3.5 py-2.5 text-sm text-muted">{emptyMessage}</li>
          ) : (
            options.map((row, i) => {
              const isActive = i === activeIndex;
              const isSelected = row.id === value;
              return (
                <li
                  key={row.id}
                  id={`${listId}-${row.id}`}
                  role="option"
                  aria-selected={isSelected}
                  className={cn(
                    "cursor-pointer px-3.5 py-2.5 text-sm text-ink",
                    isActive && "bg-surface-2",
                    isSelected && "font-semibold",
                  )}
                  onMouseEnter={() => setActiveIndex(i)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pick(row);
                  }}
                >
                  {matchOptionLabel(row)}
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
