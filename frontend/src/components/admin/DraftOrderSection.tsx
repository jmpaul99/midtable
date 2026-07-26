"use client";

import { FormEvent } from "react";
import type { League, PoolTeam, UUID } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { IconButton } from "@/components/ui/IconButton";
import { ChevronDownIcon, ChevronUpIcon, SaveIcon, UserPlusIcon } from "@/components/ui/icons";
import { Card, Muted, RankBadge, Stack } from "@/components/ui/Card";
import { Label, Select } from "@/components/ui/Field";
import { FieldHelp, LabelRow } from "@/components/ui/FieldHelp";
import { ChoiceToggle } from "@/components/ui/ChoiceToggle";

export function DraftOrderSection({
  league,
  draftOrder,
  draftStyle,
  preassignMode,
  settingsEditable,
  settingsBusy,
  teamPool,
  poolTeams,
  onMove,
  onTeamPool,
  onSaveOrder,
  onDraftStyleChange,
  onPreassignModeChange,
  onPreassign,
}: {
  league: League;
  draftOrder: UUID[];
  draftStyle: "linear" | "snake";
  preassignMode: "none" | "supported" | "optional";
  settingsEditable: boolean;
  settingsBusy?: boolean;
  teamPool: string;
  poolTeams: Record<string, PoolTeam[]>;
  onMove: (index: number, direction: -1 | 1) => void;
  onTeamPool: (id: string) => void;
  onSaveOrder: () => void;
  onDraftStyleChange: (value: "linear" | "snake") => void;
  onPreassignModeChange: (value: "none" | "supported" | "optional") => void;
  onPreassign: (e: FormEvent<HTMLFormElement>) => void;
}) {
  const multiPool = league.pools.length > 1;
  const showPreassignTools = preassignMode !== "none";
  const preassignsByMember = new Map<UUID, string[]>();
  if (showPreassignTools) {
    for (const pool of league.pools) {
      const poolLabel = pool.label || pool.key;
      for (const team of poolTeams[pool.id] || []) {
        const owner = team.current_owner;
        if (!owner || owner.acquired_via !== "preassigned") continue;
        const label = multiPool ? `${team.name} (${poolLabel})` : team.name;
        const existing = preassignsByMember.get(owner.member_id) || [];
        existing.push(label);
        preassignsByMember.set(owner.member_id, existing);
      }
    }
  }

  return (
    <Card>
      <Stack>
        <h2>{showPreassignTools ? "Draft order & preassigns" : "Draft order"}</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5 text-sm font-semibold text-muted sm:items-start">
            <LabelRow>
              Draft style
              <FieldHelp label="Draft style">
                <p className="mb-2">Controls pick order across draft rounds.</p>
                <ul className="list-disc space-y-1 pl-4">
                  <li>
                    <strong className="text-ink">Linear</strong> — same order every round
                    (1→N).
                  </li>
                  <li>
                    <strong className="text-ink">Snake</strong> — order reverses each round
                    (1→N, then N→1).
                  </li>
                </ul>
              </FieldHelp>
            </LabelRow>
            <ChoiceToggle
              label="Draft style"
              value={draftStyle}
              disabled={!settingsEditable || settingsBusy}
              options={
                [
                  { id: "linear", label: "Linear" },
                  { id: "snake", label: "Snake" },
                ] as const
              }
              onChange={onDraftStyleChange}
            />
          </div>
          <div className="flex flex-col gap-1.5 text-sm font-semibold text-muted sm:items-start">
            <LabelRow>
              Preassign mode
              <FieldHelp label="Preassign mode">
                <p className="mb-2">Whether clubs can be assigned before the live draft.</p>
                <ul className="list-disc space-y-1 pl-4">
                  <li>
                    <strong className="text-ink">None</strong> — no pre-draft assignments.
                  </li>
                  <li>
                    <strong className="text-ink">Supported</strong> — commissioners can
                    preassign clubs; every manager must have one before the draft opens.
                  </li>
                  <li>
                    <strong className="text-ink">Optional</strong> — preassign is available but
                    not required.
                  </li>
                </ul>
              </FieldHelp>
            </LabelRow>
            <ChoiceToggle
              label="Preassign mode"
              value={preassignMode}
              disabled={!settingsEditable || settingsBusy}
              options={
                [
                  { id: "none", label: "None" },
                  { id: "supported", label: "Supported" },
                  { id: "optional", label: "Optional" },
                ] as const
              }
              onChange={onPreassignModeChange}
            />
          </div>
        </div>
        <Stack gap="sm">
          {draftOrder.map((id, index) => {
            const preassigned = preassignsByMember.get(id);
            return (
              <div
                className="flex items-center gap-2 rounded-xl border border-line bg-surface-2/50 p-2.5"
                key={id}
              >
                <RankBadge value={index + 1} />
                <div className="min-w-0 flex-1">
                  <strong className="block truncate text-sm">
                    {managerLabel(league.members.find((m) => m.id === id), id)}
                  </strong>
                  {showPreassignTools && preassigned?.length ? (
                    <Muted className="truncate text-xs">{preassigned.join(" · ")}</Muted>
                  ) : null}
                </div>
                <IconButton
                  type="button"
                  variant="secondary"
                  size="icon-sm"
                  label="Move up"
                  disabled={index === 0}
                  onClick={() => onMove(index, -1)}
                >
                  <ChevronUpIcon className="size-4" />
                </IconButton>
                <IconButton
                  type="button"
                  variant="secondary"
                  size="icon-sm"
                  label="Move down"
                  disabled={index === draftOrder.length - 1}
                  onClick={() => onMove(index, 1)}
                >
                  <ChevronDownIcon className="size-4" />
                </IconButton>
              </div>
            );
          })}
        </Stack>
        <div className="flex justify-start">
          <IconButton type="button" label="Save draft order" variant="primary" onClick={onSaveOrder}>
            <SaveIcon />
          </IconButton>
        </div>
        {showPreassignTools && (
          <form className="flex flex-col gap-3" onSubmit={onPreassign}>
            <Label>
              Competition
              <Select name="pool" value={teamPool} onChange={(e) => onTeamPool(e.target.value)}>
                {league.pools.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </Label>
            <Label>
              Manager
              <Select name="member">
                {league.members.map((m) => (
                  <option value={m.id} key={m.id}>
                    {managerLabel(m)}
                  </option>
                ))}
              </Select>
            </Label>
            <Label>
              Available team
              <Select name="team" required>
                <option value="">Choose…</option>
                {(poolTeams[teamPool] || [])
                  .filter((t) => t.available)
                  .map((t) => (
                    <option value={t.id} key={t.id}>
                      {t.name}
                    </option>
                  ))}
              </Select>
            </Label>
            <div className="flex justify-start">
              <IconButton type="submit" label="Preassign team" variant="primary">
                <UserPlusIcon />
              </IconButton>
            </div>
          </form>
        )}
      </Stack>
    </Card>
  );
}
