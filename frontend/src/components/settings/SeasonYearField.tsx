"use client";

import { useState } from "react";
import { Input, Label } from "@/components/ui/Field";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { cn } from "@/lib/cn";

const SEASON_YEAR_WARNING =
  "Changing the season year tells the provider to load a different season. Clubs already linked, fixtures, and scores for this competition may no longer match — you will likely need to reload teams and re-sync. Only continue if you are sure you want a different season.";

const compactInput =
  "min-h-10 rounded-lg px-2.5 py-2 text-sm";

export function SeasonYearField({
  value,
  onChange,
  disabled = false,
  required = false,
  compact = false,
}: {
  value: number;
  onChange: (year: number) => void;
  disabled?: boolean;
  required?: boolean;
  /** Match the Slots field layout in competition rows. */
  compact?: boolean;
}) {
  const [unlocked, setUnlocked] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const locked = disabled || !unlocked;

  return (
    <>
      <Label className={cn("gap-1", !compact && "gap-1.5")}>
        Year
        <Input
          type="number"
          min={2000}
          max={2100}
          value={value}
          required={required}
          disabled={locked}
          readOnly={locked}
          onChange={(e) => onChange(Number(e.target.value))}
          className={cn(compact && compactInput)}
          title={
            unlocked || disabled
              ? undefined
              : "Locked — click Change to edit (wrong year loads the wrong season)"
          }
        />
        {!disabled && (
          <span className="text-[0.65rem] font-normal leading-snug text-muted">
            {unlocked ? (
              <span className="font-semibold text-warning">Editing unlocked</span>
            ) : (
              <button
                type="button"
                className="font-semibold text-muted underline decoration-line underline-offset-2 hover:text-ink"
                onClick={() => setConfirmOpen(true)}
              >
                Change year
              </button>
            )}
          </span>
        )}
      </Label>

      <ConfirmDialog
        open={confirmOpen}
        title="Change season year?"
        description={SEASON_YEAR_WARNING}
        confirmLabel="Unlock season year"
        cancelLabel="Keep current year"
        tone="warning"
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => {
          setConfirmOpen(false);
          setUnlocked(true);
        }}
      />
    </>
  );
}
