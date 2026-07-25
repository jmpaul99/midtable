"use client";

import { FormEvent, useMemo, useState } from "react";
import { formatNumber } from "@/lib/format";
import type { Bonus, League, PoolTeam, UUID } from "@/lib/types";
import { Empty, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import {
  AwardIcon,
  BanIcon,
  CheckIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
  XIcon,
} from "@/components/ui/icons";
import { Autocomplete } from "@/components/ui/Autocomplete";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import type { BonusTypeRow } from "./useAdminLeagueData";

type Tab = "award" | "types" | "history";

function slugKey(label: string): string {
  return label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 40);
}

export function BonusesSection({
  leagueId,
  bonusTypes,
  bonuses,
  allTeams,
  onAction,
  embedded = false,
}: {
  leagueId: UUID;
  bonusTypes: BonusTypeRow[];
  bonuses?: Bonus[];
  allTeams: Array<{ team: PoolTeam; pool: League["pools"][number] }>;
  onAction: (path: string, method: string, body?: unknown) => Promise<unknown>;
  /** When true, omit outer Card/h2 so this can nest under Scoring settings. */
  embedded?: boolean;
}) {
  const sortedTypes = useMemo(
    () =>
      [...bonusTypes].sort(
        (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.label.localeCompare(b.label),
      ),
    [bonusTypes],
  );

  const [tab, setTab] = useState<Tab>("types");
  const [awardTeamId, setAwardTeamId] = useState("");
  const [awardTypeId, setAwardTypeId] = useState("");
  const [editingId, setEditingId] = useState<UUID | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editPoints, setEditPoints] = useState("");
  const [adding, setAdding] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [newPoints, setNewPoints] = useState("");

  const teamOptions = useMemo(
    () =>
      allTeams.map(({ team, pool }) => ({
        value: team.id,
        label: `${team.name} · ${pool.label}`,
      })),
    [allTeams],
  );

  const typeOptions = useMemo(
    () =>
      sortedTypes.map((t) => ({
        value: t.id,
        label: `${t.label} (${formatNumber(t.default_points)})`,
      })),
    [sortedTypes],
  );

  const selectedType = sortedTypes.find((t) => t.id === awardTypeId);
  const awardedCount = bonuses?.length ?? 0;

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "types", label: `Types (${sortedTypes.length})` },
    { id: "award", label: "Award" },
    { id: "history", label: `Awarded (${awardedCount})` },
  ];

  function startEdit(t: BonusTypeRow) {
    setEditingId(t.id);
    setEditLabel(t.label);
    setEditPoints(String(t.default_points));
  }

  async function saveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editingId) return;
    await onAction(`/leagues/${leagueId}/bonus-types/${editingId}`, "PATCH", {
      label: editLabel.trim(),
      default_points: Number(editPoints),
    });
    setEditingId(null);
  }

  async function createType(e: FormEvent) {
    e.preventDefault();
    const label = newLabel.trim();
    if (!label) return;
    const existing = new Set(sortedTypes.map((t) => t.key));
    let key = slugKey(label) || "bonus";
    let n = 2;
    while (existing.has(key)) {
      key = `${slugKey(label)}_${n++}`;
    }
    await onAction(`/leagues/${leagueId}/bonus-types`, "POST", {
      key,
      label,
      default_points: Number(newPoints),
      sort_order: sortedTypes.length + 1,
    });
    setNewLabel("");
    setNewPoints("");
    setAdding(false);
  }

  async function award(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!awardTeamId || !awardTypeId) return;
    if (!confirm("Award this bonus using the configured points?")) return;
    const f = new FormData(e.currentTarget);
    const notes = String(f.get("notes") || "").trim();
    await onAction(`/leagues/${leagueId}/manual-bonuses`, "POST", {
      team_id: awardTeamId,
      bonus_type_id: awardTypeId,
      notes: notes || null,
    });
    e.currentTarget.reset();
    setAwardTeamId("");
    setAwardTypeId("");
    setTab("history");
  }

  const body = (
      <Stack gap="sm">
        {!embedded && <h2>Bonuses</h2>}

        <div
          className="flex gap-1 rounded-lg bg-surface-2 p-0.5"
          role="tablist"
          aria-label="Bonus sections"
        >
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "min-h-8 flex-1 rounded-md px-2 py-1 text-[0.7rem] font-bold transition sm:text-xs",
                tab === t.id ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "award" && (
          <div role="tabpanel">
            {!sortedTypes.length ? (
              <StatusBanner>
                No bonus types yet.{" "}
                <button
                  type="button"
                  className="font-bold underline"
                  onClick={() => setTab("types")}
                >
                  Add types
                </button>{" "}
                first.
              </StatusBanner>
            ) : (
              <form className="flex flex-col gap-3" onSubmit={award}>
                <Label>
                  Team
                  <Autocomplete
                    value={awardTeamId}
                    onChange={setAwardTeamId}
                    options={teamOptions}
                    required
                    placeholder="Search teams…"
                    emptyMessage="No teams match."
                  />
                </Label>
                <Label>
                  Bonus type
                  <Autocomplete
                    value={awardTypeId}
                    onChange={setAwardTypeId}
                    options={typeOptions}
                    required
                    placeholder="Search bonus types…"
                    emptyMessage="No bonus types match."
                  />
                </Label>
                {selectedType && (
                  <Muted className="text-xs">
                    Awards {formatNumber(selectedType.default_points)} pts from type config.
                  </Muted>
                )}
                <Label>
                  Notes <span className="font-normal">(optional)</span>
                  <Input name="notes" placeholder="e.g. finished 4th via GD" />
                </Label>
                <div className="flex justify-start">
                  <IconButton
                    type="submit"
                    label="Award bonus"
                    variant="primary"
                    disabled={!awardTeamId || !awardTypeId}
                  >
                    <AwardIcon />
                  </IconButton>
                </div>
              </form>
            )}
          </div>
        )}

        {tab === "types" && (
          <div role="tabpanel">
            <Stack gap="sm">
              {!sortedTypes.length ? (
                <Empty title="No bonus types yet">
                  Add types below, or use a template that includes them.
                </Empty>
              ) : (
                <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line">
                  {sortedTypes.map((t) =>
                    editingId === t.id ? (
                      <li key={t.id} className="bg-surface-2/50 p-3">
                        <form className="flex items-center gap-2" onSubmit={saveEdit}>
                          <Input
                            value={editLabel}
                            onChange={(e) => setEditLabel(e.target.value)}
                            required
                            aria-label="Label"
                            className="min-w-0 flex-1"
                          />
                          <Input
                            type="number"
                            step="0.5"
                            value={editPoints}
                            onChange={(e) => setEditPoints(e.target.value)}
                            required
                            aria-label="Points"
                            className="w-[5.5rem] shrink-0"
                          />
                          <IconButton type="submit" label="Save" variant="primary" size="icon-sm">
                            <CheckIcon className="size-4" />
                          </IconButton>
                          <IconButton
                            type="button"
                            label="Cancel"
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setEditingId(null)}
                          >
                            <XIcon className="size-4" />
                          </IconButton>
                        </form>
                      </li>
                    ) : (
                      <li
                        key={t.id}
                        className="flex flex-col gap-2 bg-surface-2/30 px-3 py-2.5 sm:flex-row sm:items-center"
                      >
                        <div className="min-w-0 flex-1">
                          <strong className="block truncate text-sm">{t.label}</strong>
                          <Muted className="truncate text-xs">
                            {formatNumber(t.default_points)} pts
                          </Muted>
                        </div>
                        <div className="flex gap-1">
                          <IconButton
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            label={`Edit ${t.label}`}
                            onClick={() => startEdit(t)}
                          >
                            <PencilIcon className="size-4" />
                          </IconButton>
                          <IconButton
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            label={`Delete ${t.label}`}
                            className="text-danger hover:bg-danger/10 hover:text-danger"
                            onClick={() => {
                              if (confirm(`Delete bonus type “${t.label}”?`)) {
                                onAction(`/leagues/${leagueId}/bonus-types/${t.id}`, "DELETE");
                              }
                            }}
                          >
                            <TrashIcon className="size-4" />
                          </IconButton>
                        </div>
                      </li>
                    ),
                  )}
                </ul>
              )}

              {adding ? (
                <form
                  className="flex items-center gap-2 rounded-xl border border-dashed border-line p-3"
                  onSubmit={createType}
                >
                  <Input
                    value={newLabel}
                    onChange={(e) => setNewLabel(e.target.value)}
                    placeholder="Name"
                    required
                    aria-label="Name"
                    className="min-w-0 flex-1"
                  />
                  <Input
                    type="number"
                    step="0.5"
                    value={newPoints}
                    onChange={(e) => setNewPoints(e.target.value)}
                    placeholder="Pts"
                    required
                    aria-label="Points"
                    className="w-[5.5rem] shrink-0"
                  />
                  <IconButton type="submit" label="Add type" variant="primary" size="icon-sm">
                    <PlusIcon className="size-4" />
                  </IconButton>
                  <IconButton
                    type="button"
                    label="Cancel"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setAdding(false)}
                  >
                    <XIcon className="size-4" />
                  </IconButton>
                </form>
              ) : (
                <div className="flex justify-start">
                  <IconButton
                    type="button"
                    variant="secondary"
                    label="Add bonus type"
                    onClick={() => setAdding(true)}
                  >
                    <PlusIcon />
                  </IconButton>
                </div>
              )}
            </Stack>
          </div>
        )}

        {tab === "history" && (
          <div role="tabpanel">
            {!bonuses?.length ? (
              <Empty title="No bonuses awarded yet" />
            ) : (
              <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line">
                {bonuses.map((b) => {
                  const typeLabel =
                    sortedTypes.find((t) => t.key === b.bonus_type)?.label || b.bonus_type;
                  return (
                    <li
                      key={b.id}
                      className="flex items-center gap-2 bg-surface-2/30 px-3 py-2.5"
                    >
                      <div className="min-w-0 flex-1">
                        <strong className="block truncate text-sm">
                          {typeLabel} · {formatNumber(b.points)}
                        </strong>
                        <Muted className="truncate text-xs">
                          {b.display_name || b.team_id}
                          {b.reason ? ` · ${b.reason}` : ""}
                        </Muted>
                      </div>
                      <IconButton
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        label="Revoke bonus"
                        className="text-danger hover:bg-danger/10 hover:text-danger"
                        onClick={() => {
                          if (confirm("Revoke this awarded bonus?")) {
                            onAction(`/leagues/${leagueId}/manual-bonuses/${b.id}`, "DELETE");
                          }
                        }}
                      >
                        <BanIcon className="size-4" />
                      </IconButton>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </Stack>
  );

  if (embedded) return body;
  return <Card>{body}</Card>;
}
