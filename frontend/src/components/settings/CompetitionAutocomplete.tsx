"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Input } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import {
  type AvailableCompetition,
  competitionDisplayLabel,
  filterAvailableCompetitions,
  findAvailableCompetition,
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
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = findAvailableCompetition(value);
  const selectedLabel = competitionDisplayLabel(value);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(selectedLabel);

  // Keep the input showing the selected competition when idle.
  useEffect(() => {
    if (!open) {
      setQuery(selectedLabel);
    }
  }, [selectedLabel, open, value]);

  const filterQuery =
    open && selectedLabel && query.trim().toLowerCase() === selectedLabel.toLowerCase()
      ? ""
      : query;

  const filtered = useMemo(
    () => filterAvailableCompetitions(filterQuery, options),
    [filterQuery, options],
  );

  const [activeIndex, setActiveIndex] = useState(0);
  useEffect(() => {
    setActiveIndex(0);
  }, [filterQuery, open]);

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

  function pick(entry: AvailableCompetition) {
    onChange(entry.code);
    setQuery(entry.label);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (disabled) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (open && filtered[activeIndex]) {
        e.preventDefault();
        pick(filtered[activeIndex]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setQuery(selectedLabel);
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <Input
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={
          open && filtered[activeIndex] ? `${listId}-${filtered[activeIndex].code}` : undefined
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
            onChange("");
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
          {filtered.length === 0 ? (
            <li className="px-3.5 py-2.5 text-sm text-muted">No competitions match.</li>
          ) : (
            filtered.map((c, i) => {
              const isActive = i === activeIndex;
              const isSelected = c.code === selected?.code;
              return (
                <li
                  key={c.code}
                  id={`${listId}-${c.code}`}
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
                    pick(c);
                  }}
                >
                  {c.label}
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
