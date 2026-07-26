"use client";

import { cn } from "@/lib/cn";

export function ChoiceToggle<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: {
  label: string;
  value: T;
  options: readonly { id: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <div
      className={cn(
        "inline-flex w-full gap-0.5 rounded-xl bg-surface-2 p-0.5 sm:w-fit sm:justify-self-start",
        disabled && "opacity-60",
      )}
      role="radiogroup"
      aria-label={label}
      aria-disabled={disabled || undefined}
    >
      {options.map((opt) => {
        const selected = value === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(opt.id)}
            className={cn(
              "min-h-10 flex-1 rounded-[0.65rem] px-3 py-1.5 text-sm font-bold transition sm:flex-none",
              selected ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink",
              disabled && "cursor-not-allowed hover:text-muted",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
