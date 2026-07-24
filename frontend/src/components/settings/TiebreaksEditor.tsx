"use client";

import { useMemo, useState } from "react";
import { IconButton } from "@/components/ui/IconButton";
import { ChevronDownIcon, ChevronUpIcon } from "@/components/ui/icons";
import { Label, Select } from "@/components/ui/Field";
import { Muted } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { AddRowButton, EditorSection, RemoveButton, RowItem, RowList } from "./chrome";
import type { TiebreakRung } from "./types";

type Option = { id: string; label: string; group: string };

const DEFAULT_EVENTS = [
  { value: "win", label: "Win" },
  { value: "draw", label: "Draw" },
  { value: "loss", label: "Loss" },
  { value: "minor_upset", label: "Minor upset" },
  { value: "major_upset", label: "Major upset" },
  { value: "major_upset_draw", label: "Major upset draw" },
];

function humanize(key: string): string {
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function rungToCriterionId(r: TiebreakRung): string {
  if (r.metric === "total_points") return "total_points";
  if (r.metric === "event_count" || r.metric === "event_points") {
    const keys = r.event_types;
    if (!keys.length) return `${r.metric}:`;
    return `${r.metric}:${keys.join("|")}`;
  }
  if (r.metric === "bonus_count" || r.metric === "bonus_points") {
    const keys = r.bonus_type_keys;
    if (!keys.length) return `${r.metric}:`;
    return `${r.metric}:${keys.join("|")}`;
  }
  return r.metric;
}

function criterionIdToRung(id: string, direction: "asc" | "desc"): TiebreakRung {
  if (id === "total_points" || !id.includes(":")) {
    return {
      metric: id === "total_points" ? "total_points" : id,
      direction,
      event_types: [],
      bonus_type_keys: [],
    };
  }
  const colon = id.indexOf(":");
  const metric = id.slice(0, colon);
  const keys = id
    .slice(colon + 1)
    .split("|")
    .map((k) => k.trim())
    .filter(Boolean);

  if (metric === "event_count" || metric === "event_points") {
    return { metric, direction, event_types: keys, bonus_type_keys: [] };
  }
  if (metric === "bonus_count" || metric === "bonus_points") {
    return { metric, direction, event_types: [], bonus_type_keys: keys };
  }
  return { metric, direction, event_types: [], bonus_type_keys: [] };
}

function buildCriteriaOptions(
  events: Array<{ value: string; label: string }>,
  bonuses: Array<{ value: string; label: string }>,
  extraCombined: Option[],
): Option[] {
  const options: Option[] = [
    { id: "total_points", label: "Total points", group: "Overall" },
  ];

  for (const e of events) {
    const countLabel =
      e.value === "win"
        ? "Wins (count)"
        : e.value === "draw"
          ? "Draws (count)"
          : e.value === "loss"
            ? "Losses (count)"
            : `${e.label} (count)`;
    const pointsLabel =
      e.value === "win"
        ? "Win points"
        : e.value === "draw"
          ? "Draw points"
          : e.value === "loss"
            ? "Loss points"
            : `${e.label} (points)`;

    options.push({
      id: `event_count:${e.value}`,
      label: countLabel,
      group: "Match events",
    });
    options.push({
      id: `event_points:${e.value}`,
      label: pointsLabel,
      group: "Match events",
    });
  }

  const upsetKeys = events.filter((e) => e.value.includes("upset")).map((e) => e.value);
  if (upsetKeys.length > 1) {
    options.push({
      id: `event_points:${upsetKeys.join("|")}`,
      label: "All upset points (combined)",
      group: "Match events",
    });
    options.push({
      id: `event_count:${upsetKeys.join("|")}`,
      label: "All upset counts (combined)",
      group: "Match events",
    });
  }

  for (const b of bonuses) {
    if (!b.value) continue;
    options.push({
      id: `bonus_points:${b.value}`,
      label: `${b.label} (points)`,
      group: "Bonuses",
    });
    options.push({
      id: `bonus_count:${b.value}`,
      label: `${b.label} (count)`,
      group: "Bonuses",
    });
  }

  // Preserve any existing combined/custom criteria not already listed
  for (const extra of extraCombined) {
    if (!options.some((o) => o.id === extra.id)) options.push(extra);
  }

  return options;
}

function labelForCriterion(
  id: string,
  options: Option[],
): string {
  const found = options.find((o) => o.id === id);
  if (found) return found.label;
  if (id === "total_points") return "Total points";
  const [metric, keysPart] = id.split(":");
  const keys = (keysPart || "").split("|").filter(Boolean);
  const kind =
    metric === "event_count"
      ? "count"
      : metric === "event_points"
        ? "points"
        : metric === "bonus_count"
          ? "count"
          : metric === "bonus_points"
            ? "points"
            : metric;
  if (keys.length) return `${keys.map(humanize).join(" + ")} (${kind})`;
  return id;
}

export function TiebreaksEditor({
  value,
  onChange,
  eventTypeOptions,
  bonusTypeOptions,
}: {
  value: TiebreakRung[];
  onChange: (next: TiebreakRung[]) => void;
  eventTypeOptions?: Array<{ value: string; label: string }>;
  bonusTypeOptions?: Array<{ value: string; label: string }>;
}) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);

  const events = eventTypeOptions?.length ? eventTypeOptions : DEFAULT_EVENTS;
  const bonuses = bonusTypeOptions || [];

  const options = useMemo(() => {
    const extras: Option[] = value.map((r) => {
      const id = rungToCriterionId(r);
      return { id, label: labelForCriterion(id, []), group: "Current" };
    });
    return buildCriteriaOptions(events, bonuses, extras);
  }, [events, bonuses, value]);

  const groups = useMemo(() => {
    const order = ["Overall", "Match events", "Bonuses", "Current"];
    const map = new Map<string, Option[]>();
    for (const opt of options) {
      const list = map.get(opt.group) || [];
      list.push(opt);
      map.set(opt.group, list);
    }
    return order.filter((g) => map.has(g)).map((g) => ({ group: g, items: map.get(g)! }));
  }, [options]);

  function setCriterion(index: number, criterionId: string) {
    const current = value[index];
    onChange(
      value.map((r, i) => (i === index ? criterionIdToRung(criterionId, current.direction) : r)),
    );
  }

  function setDirection(index: number, direction: "asc" | "desc") {
    onChange(value.map((r, i) => (i === index ? { ...r, direction } : r)));
  }

  function reorder(from: number, to: number) {
    if (from === to || from < 0 || to < 0 || from >= value.length || to >= value.length) return;
    const next = [...value];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
  }

  function addRung() {
    // Prefer an unused criterion so stacking distinct ranks is one click each
    const used = new Set(value.map(rungToCriterionId));
    const nextOpt =
      options.find((o) => o.id === "event_count:win" && !used.has(o.id)) ||
      options.find((o) => !used.has(o.id) && o.id !== "total_points") ||
      options[0];
    onChange([
      ...value,
      criterionIdToRung(nextOpt?.id || "total_points", "desc"),
    ]);
  }

  return (
    <EditorSection
      title="Leaderboard tiebreaks"
      description="Each row is one ranking rule. Use the arrows to set order — e.g. Total points → Wins → Winner’s Bonus → Major upsets."
    >
      {value.length > 0 && (
        <RowList>
          {value.map((r, index) => {
            const criterionId = rungToCriterionId(r);
            return (
              <RowItem
                key={index}
                className={cn(
                  "transition",
                  dragIndex === index && "opacity-60",
                  overIndex === index &&
                    dragIndex !== null &&
                    dragIndex !== index &&
                    "bg-brand/5",
                )}
              >
                <div
                  className="flex items-start gap-2"
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = "move";
                    if (overIndex !== index) setOverIndex(index);
                  }}
                  onDragLeave={() => {
                    if (overIndex === index) setOverIndex(null);
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    const from = dragIndex ?? Number(e.dataTransfer.getData("text/plain"));
                    reorder(from, index);
                    setDragIndex(null);
                    setOverIndex(null);
                  }}
                >
                  <div className="flex shrink-0 flex-col gap-1">
                    <IconButton
                      type="button"
                      variant="secondary"
                      size="icon-sm"
                      label={`Move tiebreak ${index + 1} up`}
                      disabled={index === 0}
                      onClick={() => reorder(index, index - 1)}
                    >
                      <ChevronUpIcon className="size-4" />
                    </IconButton>
                    <IconButton
                      type="button"
                      variant="secondary"
                      size="icon-sm"
                      label={`Move tiebreak ${index + 1} down`}
                      disabled={index === value.length - 1}
                      onClick={() => reorder(index, index + 1)}
                    >
                      <ChevronDownIcon className="size-4" />
                    </IconButton>
                    <button
                      type="button"
                      draggable
                      onDragStart={(e) => {
                        setDragIndex(index);
                        e.dataTransfer.effectAllowed = "move";
                        e.dataTransfer.setData("text/plain", String(index));
                      }}
                      onDragEnd={() => {
                        setDragIndex(null);
                        setOverIndex(null);
                      }}
                      className="mt-0.5 hidden min-h-11 min-w-11 cursor-grab select-none items-center justify-center rounded-lg border border-line bg-surface text-sm text-muted active:cursor-grabbing sm:inline-flex"
                      aria-label={`Drag to reorder tiebreak ${index + 1}`}
                      title="Drag to reorder"
                    >
                      ⋮⋮
                    </button>
                  </div>
                  <div className="grid min-w-0 flex-1 grid-cols-1 gap-2 sm:grid-cols-[auto_1fr_8.5rem]">
                    <Muted className="self-center text-xs font-bold tabular-nums">#{index + 1}</Muted>
                    <Label className="min-w-0">
                      Criterion
                      <Select
                        value={criterionId}
                        onChange={(e) => setCriterion(index, e.target.value)}
                      >
                        {!options.some((o) => o.id === criterionId) && (
                          <option value={criterionId}>
                            {labelForCriterion(criterionId, options)}
                          </option>
                        )}
                        {groups.map(({ group, items }) => (
                          <optgroup key={group} label={group}>
                            {items.map((opt) => (
                              <option key={opt.id} value={opt.id}>
                                {opt.label}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </Select>
                    </Label>
                    <Label>
                      Direction
                      <Select
                        value={r.direction}
                        onChange={(e) =>
                          setDirection(index, e.target.value === "asc" ? "asc" : "desc")
                        }
                      >
                        <option value="desc">Highest first</option>
                        <option value="asc">Lowest first</option>
                      </Select>
                    </Label>
                  </div>
                  <RemoveButton onClick={() => onChange(value.filter((_, i) => i !== index))} />
                </div>
              </RowItem>
            );
          })}
        </RowList>
      )}
      <AddRowButton label="Add ranking rule" onClick={addRung} />
    </EditorSection>
  );
}

/** Build event-type options from result events + upset threshold keys. */
export function eventOptionsFromUpsetKeys(
  thresholdKeys: string[],
): Array<{ value: string; label: string }> {
  const base = [
    { value: "win", label: "Win" },
    { value: "draw", label: "Draw" },
    { value: "loss", label: "Loss" },
  ];
  const seen = new Set(base.map((b) => b.value));
  const extras = thresholdKeys
    .filter((k) => k && !seen.has(k))
    .map((k) => {
      seen.add(k);
      return { value: k, label: humanize(k) };
    });
  return [...base, ...extras];
}
