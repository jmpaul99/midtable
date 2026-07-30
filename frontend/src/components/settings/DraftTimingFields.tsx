"use client";

import { Input, Label } from "@/components/ui/Field";
import { FieldHelp, LabelRow } from "@/components/ui/FieldHelp";
import { Muted } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

export const PICK_TIMER_PRESETS = [30, 60, 90, 120] as const;

/** Convert an ISO timestamptz to a value for `<input type="datetime-local">` (local TZ). */
export function toDatetimeLocalValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Convert datetime-local input to UTC ISO, or null when cleared. */
export function fromDatetimeLocalValue(local: string): string | null {
  const trimmed = local.trim();
  if (!trimmed) return null;
  const d = new Date(trimmed);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

/** Local datetime-local string for "now", floored to the current minute. */
export function datetimeLocalMinNow(now = new Date()): string {
  const d = new Date(now);
  d.setSeconds(0, 0);
  return toDatetimeLocalValue(d.toISOString());
}

/**
 * Latest selectable draft start: one minute before first match kickoff.
 * Returns empty when unknown or when that bound is not after `minLocal`.
 */
export function datetimeLocalMaxBeforeKickoff(
  firstMatchKickoffAt: string | null | undefined,
  minLocal?: string,
): string {
  if (!firstMatchKickoffAt) return "";
  const kickoff = new Date(firstMatchKickoffAt);
  if (Number.isNaN(kickoff.getTime())) return "";
  const max = new Date(kickoff.getTime() - 60_000);
  const maxLocal = toDatetimeLocalValue(max.toISOString());
  if (minLocal && maxLocal <= minLocal) return "";
  return maxLocal;
}

/** Client-side draft schedule rules; returns an error message or null. */
export function validateDraftScheduledLocal(
  scheduledLocal: string,
  firstMatchKickoffAt?: string | null,
  now = new Date(),
): string | null {
  const iso = fromDatetimeLocalValue(scheduledLocal);
  if (!iso) return null;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "Draft start is not a valid date and time.";
  if (when.getTime() <= now.getTime()) {
    return "Draft start must be in the future.";
  }
  if (firstMatchKickoffAt) {
    const kickoff = new Date(firstMatchKickoffAt);
    if (!Number.isNaN(kickoff.getTime()) && when.getTime() >= kickoff.getTime()) {
      return "Draft start must be before the first match of the competition.";
    }
  }
  return null;
}

export function DraftTimingFields({
  scheduledLocal,
  onScheduledLocalChange,
  pickTimerSeconds,
  onPickTimerSecondsChange,
  scheduleDisabled = false,
  timerDisabled = false,
  className,
  hint,
  firstMatchKickoffAt,
  scheduleError,
}: {
  scheduledLocal: string;
  onScheduledLocalChange: (value: string) => void;
  pickTimerSeconds: string;
  onPickTimerSecondsChange: (value: string) => void;
  scheduleDisabled?: boolean;
  timerDisabled?: boolean;
  className?: string;
  /** Override the default timing help line. */
  hint?: string;
  /** ISO kickoff of the earliest competition match; caps the schedule. */
  firstMatchKickoffAt?: string | null;
  /** Inline validation message for the schedule field. */
  scheduleError?: string | null;
}) {
  const timerNum = Number(pickTimerSeconds);
  const hasTimer = Number.isFinite(timerNum) && timerNum > 0;
  const minLocal = scheduleDisabled ? undefined : datetimeLocalMinNow();
  const maxLocal = scheduleDisabled
    ? undefined
    : datetimeLocalMaxBeforeKickoff(firstMatchKickoffAt, minLocal);

  return (
    <div className={cn("flex min-w-0 max-w-full flex-col gap-3 sm:col-span-2", className)}>
      <Muted className="text-xs leading-snug">
        {hint ??
          "Optional draft timing — not required to create the league. You can set or change these later on the Draft page."}
      </Muted>
      <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Label className="min-w-0">
          <LabelRow>
            Draft start
            <FieldHelp label="Draft start">
              When the draft should auto-open. It still waits until the roster is full, draft order
              is set, and clubs are loaded. Must be in the future
              {firstMatchKickoffAt
                ? " and before the first match of the competition"
                : ""}
              . Leave blank to open manually from the Draft page.
            </FieldHelp>
          </LabelRow>
          <Input
            type="datetime-local"
            className="min-w-0 max-w-full"
            value={scheduledLocal}
            disabled={scheduleDisabled}
            min={minLocal}
            max={maxLocal || undefined}
            onChange={(e) => onScheduledLocalChange(e.target.value)}
          />
          <Muted className="mt-1 text-xs">
            Times use your local timezone (
            {new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
              .formatToParts(new Date())
              .find((p) => p.type === "timeZoneName")?.value ?? "local"}
            ).
            {firstMatchKickoffAt
              ? " Must be before the first competition match."
              : ""}
          </Muted>
          {scheduleError ? (
            <Muted className="mt-1 text-xs font-semibold text-danger">{scheduleError}</Muted>
          ) : null}
          {!scheduleDisabled && scheduledLocal ? (
            <button
              type="button"
              className="mt-1 text-xs font-semibold text-muted underline-offset-2 hover:text-ink hover:underline"
              onClick={() => onScheduledLocalChange("")}
            >
              Clear schedule
            </button>
          ) : null}
        </Label>
        <div className="min-w-0 flex flex-col gap-2">
          <Label>
            <LabelRow>
              Seconds per pick
              <FieldHelp label="Seconds per pick">
                How long each manager has on the clock. When time runs out, the highest-ranked
                available club is auto-picked (fixed ranking list or competition table order,
                including higher domestic tiers before lower ones). Leave blank for no timer.
              </FieldHelp>
            </LabelRow>
            <Input
              type="number"
              min={1}
              step={1}
              placeholder="No timer"
              disabled={timerDisabled}
              value={pickTimerSeconds}
              onChange={(e) => onPickTimerSecondsChange(e.target.value)}
            />
          </Label>
          {!timerDisabled ? (
            <div className="flex flex-wrap gap-1.5">
              {PICK_TIMER_PRESETS.map((secs) => (
                <button
                  key={secs}
                  type="button"
                  onClick={() => onPickTimerSecondsChange(String(secs))}
                  className={cn(
                    "rounded-lg px-2.5 py-1 text-xs font-bold transition",
                    hasTimer && timerNum === secs
                      ? "bg-brand text-white"
                      : "bg-surface-2 text-muted hover:text-ink",
                  )}
                >
                  {secs}s
                </button>
              ))}
              <button
                type="button"
                onClick={() => onPickTimerSecondsChange("")}
                className={cn(
                  "rounded-lg px-2.5 py-1 text-xs font-bold transition",
                  !hasTimer
                    ? "bg-brand text-white"
                    : "bg-surface-2 text-muted hover:text-ink",
                )}
              >
                Off
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Parse form string to API payload value (null clears / omits timer). */
export function parsePickTimerSeconds(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  if (!Number.isInteger(n) || n < 1) return null;
  return n;
}
