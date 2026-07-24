"use client";

import { useState } from "react";
import { IconButton } from "@/components/ui/IconButton";
import { EraserIcon, ListChecksIcon } from "@/components/ui/icons";
import { Checkbox, Input, Label, Select } from "@/components/ui/Field";
import { Muted } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import { joinCommaList, parseCommaList, type LeaderboardPhase } from "./types";

const blankPhase = (): LeaderboardPhase => ({
  key: "",
  label: "",
  match_filter: { type: "matchweek_range", from: 1, to: 19 },
  include_bonus_types: [],
});

function humanize(key: string): string {
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function BonusTypePicker({
  selected,
  options,
  onChange,
}: {
  selected: string[];
  options: Array<{ value: string; label: string }>;
  onChange: (next: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const known = new Map(options.filter((o) => o.value).map((o) => [o.value, o.label || o.value]));
  const orphanKeys = selected.filter((k) => k && !known.has(k));
  const items = [
    ...options.filter((o) => o.value),
    ...orphanKeys.map((k) => ({ value: k, label: `${humanize(k)} (missing)` })),
  ];
  const selectedSet = new Set(selected);
  const q = query.trim().toLowerCase();
  const visible = q
    ? items.filter(
        (o) =>
          o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q),
      )
    : items;
  const allKeys = items.map((o) => o.value);
  const allSelected = allKeys.length > 0 && allKeys.every((k) => selectedSet.has(k));

  function toggle(key: string) {
    if (selectedSet.has(key)) {
      onChange(selected.filter((k) => k !== key));
    } else {
      onChange([...selected, key]);
    }
  }

  if (!items.length) {
    return (
      <Muted className="rounded-lg border border-dashed border-line px-3 py-2 text-xs">
        No bonus types defined yet. Add them under Bonuses first.
      </Muted>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {items.length > 8 && (
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter bonuses…"
            className="min-h-11 flex-1 basis-40 text-sm"
            aria-label="Filter bonus types"
          />
        )}
        <div className="ml-auto flex gap-1">
          <IconButton
            type="button"
            variant="ghost"
            size="icon-sm"
            label="Select all"
            onClick={() => onChange(allKeys)}
            disabled={allSelected}
          >
            <ListChecksIcon className="size-4" />
          </IconButton>
          <IconButton
            type="button"
            variant="ghost"
            size="icon-sm"
            label="Clear"
            onClick={() => onChange([])}
            disabled={!selected.length}
          >
            <EraserIcon className="size-4" />
          </IconButton>
        </div>
      </div>
      <div className="max-h-56 overflow-y-auto overscroll-contain rounded-lg border border-line bg-surface">
        {visible.length === 0 ? (
          <Muted className="px-3 py-4 text-center text-xs">No bonuses match “{query.trim()}”</Muted>
        ) : (
          <ul className="grid grid-cols-1 divide-y divide-line sm:grid-cols-2 sm:divide-y-0">
            {visible.map((opt) => {
              const checked = selectedSet.has(opt.value);
              return (
                <li key={opt.value} className="sm:border-b sm:border-line">
                  <label
                    className={cn(
                      "flex min-h-11 cursor-pointer items-center gap-2.5 px-3 py-2 text-sm transition",
                      checked ? "bg-brand/10 text-ink" : "text-muted hover:bg-surface-2 hover:text-ink",
                    )}
                  >
                    <Checkbox
                      checked={checked}
                      onChange={() => toggle(opt.value)}
                    />
                    <span className="min-w-0 truncate font-medium" title={opt.label}>
                      {opt.label}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <Muted className="text-xs">
        {selected.length
          ? `${selected.length} of ${items.length} bonus type${items.length === 1 ? "" : "s"} included`
          : "None selected — match points only for this phase"}
      </Muted>
    </div>
  );
}

export function PhasesEditor({
  value,
  onChange,
  bonusTypeOptions,
}: {
  value: LeaderboardPhase[];
  onChange: (next: LeaderboardPhase[]) => void;
  bonusTypeOptions?: Array<{ value: string; label: string }>;
}) {
  function update(index: number, patch: Partial<LeaderboardPhase>) {
    onChange(value.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  const bonuses = bonusTypeOptions || [];

  return (
    <EditorSection
      title="Leaderboard phases"
      description="Split-season standings windows (e.g. matchweeks 1–19). Full season is always available."
    >
      {value.length > 0 && (
        <RowList>
          {value.map((p, index) => {
            const filterType = p.match_filter.type;
            return (
              <RowItem key={index}>
                <div className="flex flex-col gap-2">
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <Label>
                      Key
                      <Input
                        value={p.key}
                        onChange={(e) => update(index, { key: e.target.value })}
                        placeholder="mw1_19"
                      />
                    </Label>
                    <Label>
                      Label
                      <Input
                        value={p.label}
                        onChange={(e) => update(index, { label: e.target.value })}
                        placeholder="Matchweeks 1–19"
                      />
                    </Label>
                  </div>
                  <Label>
                    Match filter
                    <Select
                      value={filterType}
                      onChange={(e) => {
                        const type = e.target.value;
                        update(index, {
                          match_filter:
                            type === "stage_in"
                              ? { type: "stage_in", stages: [] }
                              : { type: "matchweek_range", from: 1, to: 19 },
                        });
                      }}
                    >
                      <option value="matchweek_range">Matchweek range</option>
                      <option value="stage_in">Stages</option>
                    </Select>
                  </Label>
                  {filterType === "matchweek_range" ? (
                    <div className="grid grid-cols-2 gap-2">
                      <Label>
                        From MW
                        <Input
                          type="number"
                          min={1}
                          value={p.match_filter.type === "matchweek_range" ? p.match_filter.from : 1}
                          onChange={(e) =>
                            update(index, {
                              match_filter: {
                                type: "matchweek_range",
                                from: Number(e.target.value),
                                to:
                                  p.match_filter.type === "matchweek_range"
                                    ? p.match_filter.to
                                    : 19,
                              },
                            })
                          }
                        />
                      </Label>
                      <Label>
                        To MW
                        <Input
                          type="number"
                          min={1}
                          value={p.match_filter.type === "matchweek_range" ? p.match_filter.to : 19}
                          onChange={(e) =>
                            update(index, {
                              match_filter: {
                                type: "matchweek_range",
                                from:
                                  p.match_filter.type === "matchweek_range"
                                    ? p.match_filter.from
                                    : 1,
                                to: Number(e.target.value),
                              },
                            })
                          }
                        />
                      </Label>
                    </div>
                  ) : (
                    <Label>
                      Stages (comma-separated)
                      <Input
                        value={
                          p.match_filter.type === "stage_in"
                            ? joinCommaList(p.match_filter.stages)
                            : ""
                        }
                        onChange={(e) =>
                          update(index, {
                            match_filter: {
                              type: "stage_in",
                              stages: parseCommaList(e.target.value),
                            },
                          })
                        }
                        placeholder="GROUP_STAGE, LAST_16"
                      />
                    </Label>
                  )}
                  <div>
                    <Muted className="mb-1.5 text-xs font-bold uppercase tracking-wide">
                      Include bonus types
                    </Muted>
                    <BonusTypePicker
                      selected={p.include_bonus_types}
                      options={bonuses}
                      onChange={(include_bonus_types) => update(index, { include_bonus_types })}
                    />
                  </div>
                  <div className="flex justify-end">
                    <RemoveButton onClick={() => onChange(value.filter((_, i) => i !== index))} />
                  </div>
                </div>
              </RowItem>
            );
          })}
        </RowList>
      )}
      <AddRowButton label="Add phase" onClick={() => onChange([...value, blankPhase()])} />
    </EditorSection>
  );
}
