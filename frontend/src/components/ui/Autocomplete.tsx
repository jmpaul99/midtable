"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Input } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import { useComboboxDismiss } from "@/lib/useComboboxDismiss";

export type AutocompleteOption = {
  value: string;
  label: string;
  /** Extra strings matched by search (not shown in the list). */
  keywords?: string[];
};

export type AutocompleteLoadResult = {
  items: AutocompleteOption[];
  hasMore: boolean;
  /** Cursor for the next page when it differs from `offset + items.length`. */
  nextOffset?: number;
};

function filterOptions(query: string, options: AutocompleteOption[]): AutocompleteOption[] {
  const q = query.trim().toLowerCase();
  if (!q) return options;
  return options.filter(
    (o) =>
      o.label.toLowerCase().includes(q) ||
      o.value.toLowerCase().includes(q) ||
      (o.keywords?.some((k) => k.toLowerCase().includes(q)) ?? false),
  );
}

export function Autocomplete({
  value,
  onChange,
  options,
  loadOptions,
  disabled = false,
  required = false,
  placeholder = "Search…",
  emptyMessage = "No matches.",
  loadingEmptyMessage = "Searching…",
  idleEmptyMessage,
  id,
  className,
  name,
  selectedLabel: selectedLabelProp,
  loadMoreLabel = "Show more",
}: {
  value: string;
  onChange: (value: string) => void;
  /** Sync options. Ignored when `loadOptions` is set. */
  options?: AutocompleteOption[];
  /**
   * Async options loader. When set, Autocomplete owns debounce, cancel, and
   * pagination via offset. Sync `options` are ignored.
   */
  loadOptions?: (
    query: string,
    opts: { offset: number },
  ) => Promise<AutocompleteLoadResult>;
  disabled?: boolean;
  required?: boolean;
  placeholder?: string;
  emptyMessage?: string;
  loadingEmptyMessage?: string;
  /** Async idle (no search query) empty copy; falls back to emptyMessage. */
  idleEmptyMessage?: string;
  id?: string;
  className?: string;
  /** Optional hidden input name for native form posts. */
  name?: string;
  /**
   * Override display label for the selected value (e.g. when the row is not
   * in the current option list).
   */
  selectedLabel?: string;
  loadMoreLabel?: string;
}) {
  const asyncMode = typeof loadOptions === "function";
  const syncOptions = options ?? [];
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = syncOptions.find((o) => o.value === value);
  const selectedLabel = selectedLabelProp ?? selected?.label ?? "";
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(selectedLabel);
  const [asyncOptions, setAsyncOptions] = useState<AutocompleteOption[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const fetchGeneration = useRef(0);

  useEffect(() => {
    if (!open) {
      setQuery(selectedLabel);
    }
  }, [selectedLabel, open, value]);

  const filterQuery =
    open && selectedLabel && query.trim().toLowerCase() === selectedLabel.toLowerCase()
      ? ""
      : query;

  const searchTerm = filterQuery.trim();

  const loadPage = useCallback(
    async (nextOffset: number, append: boolean, search: string, generation: number) => {
      if (!loadOptions) return;
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
        setLoadingMore(false);
      }
      try {
        const page = await loadOptions(search, { offset: nextOffset });
        if (generation !== fetchGeneration.current) return;
        setAsyncOptions((prev) => {
          if (!append) return page.items;
          const seen = new Set(prev.map((o) => o.value));
          return [...prev, ...page.items.filter((o) => !seen.has(o.value))];
        });
        setHasMore(page.hasMore);
        setOffset(page.nextOffset ?? nextOffset + page.items.length);
      } catch {
        if (generation !== fetchGeneration.current) return;
        if (!append) {
          setAsyncOptions([]);
          setHasMore(false);
          setOffset(0);
        }
      } finally {
        if (generation === fetchGeneration.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [loadOptions],
  );

  useEffect(() => {
    if (!asyncMode || !open || disabled) return;
    const generation = ++fetchGeneration.current;
    setLoadingMore(false);
    const handle = window.setTimeout(() => {
      setAsyncOptions([]);
      setHasMore(false);
      setOffset(0);
      void loadPage(0, false, searchTerm, generation);
    }, searchTerm ? 250 : 0);
    return () => {
      window.clearTimeout(handle);
      fetchGeneration.current += 1;
    };
  }, [asyncMode, open, searchTerm, disabled, loadPage]);

  const filtered = useMemo(() => {
    if (asyncMode) return asyncOptions;
    return filterOptions(filterQuery, syncOptions);
  }, [asyncMode, asyncOptions, filterQuery, syncOptions]);

  const [activeIndex, setActiveIndex] = useState(0);
  useEffect(() => {
    setActiveIndex(0);
  }, [filterQuery, open, asyncOptions]);

  const dismiss = useCallback(() => {
    setOpen(false);
    setQuery(selectedLabel);
  }, [selectedLabel]);
  useComboboxDismiss(rootRef, dismiss);

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
      dismiss();
    }
  }

  const listEmptyMessage =
    asyncMode && loading
      ? loadingEmptyMessage
      : asyncMode && !searchTerm && idleEmptyMessage
        ? idleEmptyMessage
        : emptyMessage;

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
            <li className="px-3.5 py-2.5 text-sm text-muted">{listEmptyMessage}</li>
          ) : (
            <>
              {filtered.map((opt, i) => {
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
              })}
              {asyncMode && hasMore && (
                <li className="border-t border-line px-2 py-1.5">
                  <button
                    type="button"
                    className="w-full rounded-lg px-2 py-1.5 text-left text-sm font-semibold text-brand hover:bg-surface-2 disabled:opacity-60"
                    disabled={loadingMore || loading}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      if (loadingMore || loading) return;
                      const pageOffset = offset;
                      const generation = ++fetchGeneration.current;
                      void loadPage(pageOffset, true, searchTerm, generation);
                    }}
                  >
                    {loadingMore ? "Loading…" : loadMoreLabel}
                  </button>
                </li>
              )}
            </>
          )}
        </ul>
      )}
    </div>
  );
}
