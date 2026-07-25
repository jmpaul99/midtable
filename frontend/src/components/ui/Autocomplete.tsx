"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Input } from "@/components/ui/Field";
import { cn } from "@/lib/cn";

export type AutocompleteOption = {
  value: string;
  label: string;
};

function filterOptions(query: string, options: AutocompleteOption[]): AutocompleteOption[] {
  const q = query.trim().toLowerCase();
  if (!q) return options;
  return options.filter(
    (o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q),
  );
}

export function Autocomplete({
  value,
  onChange,
  options,
  disabled = false,
  required = false,
  placeholder = "Search…",
  emptyMessage = "No matches.",
  id,
  className,
  name,
}: {
  value: string;
  onChange: (value: string) => void;
  options: AutocompleteOption[];
  disabled?: boolean;
  required?: boolean;
  placeholder?: string;
  emptyMessage?: string;
  id?: string;
  className?: string;
  /** Optional hidden input name for native form posts. */
  name?: string;
}) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);
  const selectedLabel = selected?.label ?? "";
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(selectedLabel);

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
    () => filterOptions(filterQuery, options),
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

  function pick(entry: AutocompleteOption) {
    onChange(entry.value);
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
      {name ? <input type="hidden" name={name} value={value} /> : null}
      <Input
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={
          open && filtered[activeIndex] ? `${listId}-${filtered[activeIndex].value}` : undefined
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
            <li className="px-3.5 py-2.5 text-sm text-muted">{emptyMessage}</li>
          ) : (
            filtered.map((opt, i) => {
              const isActive = i === activeIndex;
              const isSelected = opt.value === value;
              return (
                <li
                  key={opt.value}
                  id={`${listId}-${opt.value}`}
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
                    pick(opt);
                  }}
                >
                  {opt.label}
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
