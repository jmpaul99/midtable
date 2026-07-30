"use client";

import { useId, useState } from "react";
import { Input, Label, Select } from "@/components/ui/Field";
import { Muted } from "@/components/ui/Card";
import { ChevronDownIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { MATCH_STAGES, matchStageLabel } from "@/lib/matchStages";
import { AddRowButton, RemoveButton } from "./chrome";
import {
  EMPTY_STAGE_RESULT_POINTS,
  defaultResolvedPoints,
  resolveResultPoints,
  stageHasOvertimeOverrides,
  stageOverrideCount,
  stageOverrideKeys,
  type ResultPointKey,
  type ResultPoints,
  type StageResultPoints,
} from "./types";

const FIELD_LABELS: Record<ResultPointKey, string> = {
  win: "Win",
  draw: "Draw",
  loss: "Loss",
  win_et: "Win ET",
  loss_et: "Loss ET",
  win_pk: "Win PK",
  loss_pk: "Loss PK",
};

function stageSummary(value: ResultPoints, code: string): string {
  const stage = value.by_stage[code];
  const keys = stageOverrideKeys(stage);
  if (!keys.length) return "Same as default";
  return keys.map((k) => `${FIELD_LABELS[k]} ${stage![k]}`).join(" · ");
}

/** Empty = inherited value. Placeholder shows what empty resolves to. */
function DiffField({
  label,
  fieldKey,
  stage,
  placeholder,
  onPatch,
}: {
  label: string;
  fieldKey: ResultPointKey;
  stage: StageResultPoints;
  placeholder: number;
  onPatch: (patch: Partial<StageResultPoints>) => void;
}) {
  const current = stage[fieldKey];
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
          onPatch({ [fieldKey]: raw === "" ? null : Number(raw) });
        }}
      />
    </Label>
  );
}

function StageOvertimePanel({
  stage,
  resolved,
  onPatch,
}: {
  stage: StageResultPoints;
  resolved: Record<ResultPointKey, number>;
  onPatch: (patch: Partial<StageResultPoints>) => void;
}) {
  const panelId = useId();
  const hasOverrides = stageHasOvertimeOverrides(stage);
  const [open, setOpen] = useState(hasOverrides);

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface/60">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-10 w-full items-center justify-between gap-3 px-3 py-2 text-left transition hover:bg-surface-2"
      >
        <span className="min-w-0">
          <span className="block text-xs font-semibold text-ink">Extra time &amp; penalties</span>
          <Muted className="text-[0.7rem]">
            {hasOverrides
              ? "Different from stage win/loss"
              : "Empty inherits this stage's win/loss, then Default"}
          </Muted>
        </span>
        <ChevronDownIcon
          className={cn(
            "size-4 shrink-0 text-muted transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>
      {open ? (
        <div id={panelId} className="border-t border-line px-3 pb-3 pt-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-muted">
                Extra time
              </p>
              <div className="grid grid-cols-2 gap-2">
                <DiffField
                  label="Win"
                  fieldKey="win_et"
                  stage={stage}
                  placeholder={resolved.win_et}
                  onPatch={onPatch}
                />
                <DiffField
                  label="Loss"
                  fieldKey="loss_et"
                  stage={stage}
                  placeholder={resolved.loss_et}
                  onPatch={onPatch}
                />
              </div>
            </div>
            <div>
              <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-muted">
                Penalties
              </p>
              <div className="grid grid-cols-2 gap-2">
                <DiffField
                  label="Win"
                  fieldKey="win_pk"
                  stage={stage}
                  placeholder={resolved.win_pk}
                  onPatch={onPatch}
                />
                <DiffField
                  label="Loss"
                  fieldKey="loss_pk"
                  stage={stage}
                  placeholder={resolved.loss_pk}
                  onPatch={onPatch}
                />
              </div>
            </div>
          </div>
          <Muted className="mt-2 text-[0.7rem]">
            Empty fields inherit this stage's win/loss, then Default (placeholders).
          </Muted>
        </div>
      ) : null}
    </div>
  );
}

function StageCard({
  code,
  value,
  onChange,
  usedCodes,
}: {
  code: string;
  value: ResultPoints;
  onChange: (next: ResultPoints) => void;
  usedCodes: Set<string>;
}) {
  const stage = value.by_stage[code] ?? EMPTY_STAGE_RESULT_POINTS;
  const defaults = defaultResolvedPoints(value);
  const resolved = resolveResultPoints(value, code);
  const [expanded, setExpanded] = useState(() => stageOverrideKeys(stage).length === 0);
  const cardId = useId();
  const available = MATCH_STAGES.filter((s) => s.code === code || !usedCodes.has(s.code));
  const known = available.some((s) => s.code === code);
  const options = known
    ? available
    : [{ code, label: matchStageLabel(code) }, ...available];

  function patchStage(patch: Partial<StageResultPoints>) {
    const nextStage: StageResultPoints = { ...stage, ...patch };
    const by_stage = { ...value.by_stage };
    if (stageOverrideKeys(nextStage).length > 0) {
      by_stage[code] = nextStage;
    } else {
      by_stage[code] = { ...EMPTY_STAGE_RESULT_POINTS };
    }
    onChange({ ...value, by_stage });
  }

  function renameStage(nextCode: string) {
    if (!nextCode || nextCode === code) return;
    const by_stage = { ...value.by_stage };
    const current = by_stage[code] ?? EMPTY_STAGE_RESULT_POINTS;
    delete by_stage[code];
    by_stage[nextCode] = current;
    onChange({ ...value, by_stage });
  }

  function remove() {
    const by_stage = { ...value.by_stage };
    delete by_stage[code];
    onChange({ ...value, by_stage });
  }

  return (
    <li className="bg-surface-2/30">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={cardId}
        onClick={() => setExpanded((v) => !v)}
        className="flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition hover:bg-surface-2"
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-ink">{matchStageLabel(code)}</span>
          <Muted className="truncate text-xs">{stageSummary(value, code)}</Muted>
        </span>
        <ChevronDownIcon
          className={cn(
            "size-5 shrink-0 text-muted transition-transform duration-200",
            expanded && "rotate-180",
          )}
        />
      </button>
      {expanded ? (
        <div id={cardId} className="space-y-3 border-t border-line px-3 pb-3 pt-3">
          <div className="flex items-end gap-2">
            <Label className="min-w-0 flex-1">
              Stage
              <Select value={code} onChange={(e) => renameStage(e.target.value)}>
                {options.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </Label>
            <RemoveButton onClick={remove} label="Remove stage" />
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <DiffField
              label="Win"
              fieldKey="win"
              stage={stage}
              placeholder={defaults.win}
              onPatch={patchStage}
            />
            <DiffField
              label="Draw"
              fieldKey="draw"
              stage={stage}
              placeholder={defaults.draw}
              onPatch={patchStage}
            />
            <DiffField
              label="Loss"
              fieldKey="loss"
              stage={stage}
              placeholder={defaults.loss}
              onPatch={patchStage}
            />
          </div>
          <Muted className="text-xs">
            Only fill what should differ. Empty win/draw/loss use Default; empty ET/PK
            inherit this stage's win/loss, then Default (placeholders).
          </Muted>
          <StageOvertimePanel stage={stage} resolved={resolved} onPatch={patchStage} />
        </div>
      ) : null}
    </li>
  );
}

export function StagePointsOverrides({
  value,
  onChange,
}: {
  value: ResultPoints;
  onChange: (next: ResultPoints) => void;
}) {
  const panelId = useId();
  const codes = Object.keys(value.by_stage || {});
  const customized = stageOverrideCount(value);
  const [open, setOpen] = useState(codes.length > 0);
  const used = new Set(codes);
  const available = MATCH_STAGES.filter((s) => !used.has(s.code));

  function addStage() {
    const next = available[0];
    if (!next) return;
    onChange({
      ...value,
      by_stage: {
        ...value.by_stage,
        [next.code]: { ...EMPTY_STAGE_RESULT_POINTS },
      },
    });
    setOpen(true);
  }

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface-2/40">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition hover:bg-surface-2"
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-ink">Different by stage</span>
          <Muted className="text-xs">
            {customized
              ? `${customized} stage${customized === 1 ? "" : "s"} differ from default`
              : "Optional — fill only the points that should change for a stage"}
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
        <div id={panelId} className="space-y-3 border-t border-line px-3 pb-3 pt-3">
          <Muted className="text-xs">
            Defaults above apply to every match. Add a stage and enter only the values that
            should be different. Clear a field to go back to default.
          </Muted>
          {codes.length > 0 ? (
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line">
              {codes.map((code) => (
                <StageCard
                  key={code}
                  code={code}
                  value={value}
                  onChange={onChange}
                  usedCodes={used}
                />
              ))}
            </ul>
          ) : (
            <Muted className="rounded-lg border border-dashed border-line px-3 py-2 text-xs">
              No stages yet — every match uses Default.
            </Muted>
          )}
          <AddRowButton
            label="Add stage"
            onClick={addStage}
            className={available.length === 0 ? "pointer-events-none opacity-50" : undefined}
          />
          {available.length === 0 && codes.length > 0 ? (
            <Muted className="text-xs">All known stages have been added.</Muted>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
