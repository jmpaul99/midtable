"use client";

import { useId, useState } from "react";
import { Input, Label } from "@/components/ui/Field";
import { Muted } from "@/components/ui/Card";
import { ChevronDownIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { EditorSection } from "./chrome";
import { StagePointsOverrides } from "./StagePointsOverrides";
import { hasOvertimeOverrides, type ResultPoints } from "./types";

type OvertimeKey = "win_et" | "loss_et" | "win_pk" | "loss_pk";

function OvertimeField({
  label,
  fieldKey,
  value,
  placeholder,
  onChange,
}: {
  label: string;
  fieldKey: OvertimeKey;
  value: ResultPoints;
  placeholder: number;
  onChange: (next: ResultPoints) => void;
}) {
  const current = value[fieldKey];
  return (
    <Label className="text-xs">
      {label}
      <Input
        type="number"
        step="0.5"
        className="min-h-10 text-sm"
        placeholder={String(placeholder)}
        value={current ?? ""}
        onChange={(e) => {
          const raw = e.target.value;
          onChange({
            ...value,
            [fieldKey]: raw === "" ? null : Number(raw),
          });
        }}
      />
    </Label>
  );
}

export function ResultPointsEditor({
  value,
  onChange,
}: {
  value: ResultPoints;
  onChange: (next: ResultPoints) => void;
}) {
  const panelId = useId();
  const [open, setOpen] = useState(() => hasOvertimeOverrides(value));
  const hasOverrides = hasOvertimeOverrides(value);

  return (
    <EditorSection
      title="Result points"
      description="Set the normal win / draw / loss (and optional ET/PK). Then, only if needed, override specific stages below."
    >
      <div className="rounded-xl border border-line bg-surface-2/30 p-3">
        <div className="mb-3">
          <p className="text-sm font-semibold text-ink">Default</p>
          <Muted className="text-xs">
            These points apply to every match. Stage rows below only change what you fill in.
          </Muted>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Label>
            Win
            <Input
              type="number"
              step="0.5"
              value={value.win}
              onChange={(e) => onChange({ ...value, win: Number(e.target.value) })}
            />
          </Label>
          <Label>
            Draw
            <Input
              type="number"
              step="0.5"
              value={value.draw}
              onChange={(e) => onChange({ ...value, draw: Number(e.target.value) })}
            />
          </Label>
          <Label>
            Loss
            <Input
              type="number"
              step="0.5"
              value={value.loss}
              onChange={(e) => onChange({ ...value, loss: Number(e.target.value) })}
            />
          </Label>
        </div>

        <div className="mt-3 overflow-hidden rounded-xl border border-line bg-surface/60">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((v) => !v)}
            className="flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition hover:bg-surface-2"
          >
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-ink">
                Extra time &amp; penalties
              </span>
              <Muted className="text-xs">
                {hasOverrides
                  ? "Custom overrides set"
                  : "Optional — defaults to win/loss above"}
              </Muted>
            </span>
            <ChevronDownIcon
              className={cn(
                "size-5 shrink-0 text-muted transition-transform duration-200",
                open && "rotate-180",
              )}
            />
          </button>

          {open ? (
            <div id={panelId} className="border-t border-line px-3 pb-3 pt-3">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-line bg-surface-2/40 p-3">
                  <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">
                    Extra time
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <OvertimeField
                      label="Win"
                      fieldKey="win_et"
                      value={value}
                      placeholder={value.win}
                      onChange={onChange}
                    />
                    <OvertimeField
                      label="Loss"
                      fieldKey="loss_et"
                      value={value}
                      placeholder={value.loss}
                      onChange={onChange}
                    />
                  </div>
                </div>
                <div className="rounded-xl border border-line bg-surface-2/40 p-3">
                  <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">
                    Penalties
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <OvertimeField
                      label="Win"
                      fieldKey="win_pk"
                      value={value}
                      placeholder={value.win}
                      onChange={onChange}
                    />
                    <OvertimeField
                      label="Loss"
                      fieldKey="loss_pk"
                      value={value}
                      placeholder={value.loss}
                      onChange={onChange}
                    />
                  </div>
                </div>
              </div>
              <Muted className="mt-2 text-xs">Empty fields fall back to Win / Loss above.</Muted>
            </div>
          ) : null}
        </div>
      </div>

      <StagePointsOverrides value={value} onChange={onChange} />
    </EditorSection>
  );
}
