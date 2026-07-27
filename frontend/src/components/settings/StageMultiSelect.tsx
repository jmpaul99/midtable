"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { XIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { useComboboxDismiss } from "@/lib/useComboboxDismiss";
import {
  MATCH_STAGES,
  filterMatchStages,
  matchStageLabel,
  type MatchStage,
} from "@/lib/matchStages";

const KNOWN_CODES = new Set(MATCH_STAGES.map((s) => s.code));

export function StageMultiSelect({
  value,
  onChange,
  placeholder = "Search stages…",
  className,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  className?: string;
}) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const selectedSet = useMemo(() => new Set(value), [value]);
  const filtered = useMemo(
    () => filterMatchStages(query, selectedSet),
    [query, selectedSet],
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [query, open, filtered.length]);

  const dismiss = useCallback(() => {
    setOpen(false);
    setQuery("");
  }, []);
  useComboboxDismiss(rootRef, dismiss);

  function add(stage: MatchStage) {
    if (selectedSet.has(stage.code)) return;
    onChange([...value, stage.code]);
    setQuery("");
    inputRef.current?.focus();
  }

  function remove(code: string) {
    onChange(value.filter((c) => c !== code));
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
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
        add(filtered[activeIndex]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
    } else if (e.key === "Backspace" && !query && value.length) {
      remove(value[value.length - 1]!);
    }
  }

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <div
        className={cn(
          "flex min-h-11 w-full flex-wrap items-center gap-1.5 rounded-xl border border-line bg-surface px-2 py-1.5 text-base text-ink transition",
          "focus-within:outline-none focus-within:ring-2 focus-within:ring-brand/40",
        )}
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((code) => (
          <span
            key={code}
            className="inline-flex max-w-full items-center gap-1 rounded-lg bg-surface-2 px-2 py-1 text-sm font-medium text-ink"
          >
            <span className="min-w-0 truncate" title={code}>
              {matchStageLabel(code)}
              {!KNOWN_CODES.has(code) ? " (unknown)" : ""}
            </span>
            <button
              type="button"
              className="shrink-0 rounded p-0.5 text-muted transition hover:bg-danger/10 hover:text-danger"
              aria-label={`Remove ${matchStageLabel(code)}`}
              onClick={(e) => {
                e.stopPropagation();
                remove(code);
              }}
            >
              <XIcon className="size-3.5" />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={
            open && filtered[activeIndex] ? `${listId}-${filtered[activeIndex].code}` : undefined
          }
          autoComplete="off"
          placeholder={value.length ? "" : placeholder}
          className="min-w-[7rem] flex-1 border-0 bg-transparent px-1.5 py-1 text-base text-ink outline-none placeholder:text-muted/70"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto overscroll-contain rounded-xl border border-line bg-surface py-1 shadow-lg"
        >
          {filtered.length === 0 ? (
            <li className="px-3.5 py-2.5 text-sm text-muted">
              {selectedSet.size >= MATCH_STAGES.length
                ? "All stages selected."
                : "No stages match."}
            </li>
          ) : (
            filtered.map((stage, i) => {
              const isActive = i === activeIndex;
              return (
                <li
                  key={stage.code}
                  id={`${listId}-${stage.code}`}
                  role="option"
                  aria-selected={false}
                  className={cn(
                    "cursor-pointer px-3.5 py-2.5 text-sm text-ink",
                    isActive && "bg-surface-2",
                  )}
                  onMouseEnter={() => setActiveIndex(i)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    add(stage);
                  }}
                >
                  {stage.label}
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
