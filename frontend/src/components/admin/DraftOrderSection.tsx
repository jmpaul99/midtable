"use client";

import { FormEvent } from "react";
import type { League, PoolTeam, UUID } from "@/lib/types";
import { managerLabel, managerOptionLabel } from "@/lib/types";
import { IconButton } from "@/components/ui/IconButton";
import { Button } from "@/components/ui/Button";
import { ChevronDownIcon, ChevronUpIcon, SaveIcon, UserPlusIcon } from "@/components/ui/icons";
import { Card, Muted, RankBadge, Stack } from "@/components/ui/Card";
import { Input, Label, Select } from "@/components/ui/Field";
import { FieldHelp, LabelRow } from "@/components/ui/FieldHelp";
import { ChoiceToggle } from "@/components/ui/ChoiceToggle";
import { PoolFilterSelect } from "@/components/ui/PoolFilterSelect";
import { DraftTimingFields } from "@/components/settings/DraftTimingFields";

export type PreassignMode = "off" | "optional" | "required";

export function DraftOrderSection({
  league,
  draftOrder,
  draftStyle,
  preassignMode,
  preassignCount,
  settingsEditable,
  settingsBusy,
  teamPool,
  poolTeams,
  scheduledLocal,
  pickTimerSeconds,
  scheduleEditable,
  timerEditable,
  onMove,
  onTeamPool,
  onDraftStyleChange,
  onPreassignModeChange,
  onPreassignCountChange,
  onPreassign,
  onScheduledLocalChange,
  onPickTimerSecondsChange,
  onSave,
}: {
  league: League;
  draftOrder: UUID[];
  draftStyle: "linear" | "snake";
  preassignMode: PreassignMode;
  preassignCount: number;
  settingsEditable: boolean;
  settingsBusy?: boolean;
  teamPool: string;
  poolTeams: Record<string, PoolTeam[]>;
  scheduledLocal: string;
  pickTimerSeconds: string;
  scheduleEditable: boolean;
  timerEditable: boolean;
  onMove: (index: number, direction: -1 | 1) => void;
  onTeamPool: (id: string) => void;
  onDraftStyleChange: (value: "linear" | "snake") => void;
  onPreassignModeChange: (value: PreassignMode) => void;
  onPreassignCountChange: (value: number) => void;
  onPreassign: (e: FormEvent<HTMLFormElement>) => void;
  onScheduledLocalChange: (value: string) => void;
  onPickTimerSecondsChange: (value: string) => void;
  onSave: () => void;
}) {
  const multiPool = league.pools.length > 1;
  const showPreassignTools = preassignMode !== "off";
  const countMin = preassignMode === "required" ? 1 : 0;
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

  const timingEditable = scheduleEditable || timerEditable;

  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <Stack className="min-w-0">
        <h2>Draft settings</h2>
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

        <DraftTimingFields
          scheduledLocal={scheduledLocal}
          onScheduledLocalChange={onScheduledLocalChange}
          pickTimerSeconds={pickTimerSeconds}
          onPickTimerSecondsChange={onPickTimerSecondsChange}
          scheduleDisabled={!scheduleEditable || settingsBusy}
          timerDisabled={!timerEditable || settingsBusy}
          hint="Schedule auto-open and the pick clock. Schedule can only be changed before the draft opens."
        />

        <Stack gap="sm">
          <h3 className="text-sm font-bold text-ink">Draft order</h3>
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
                  disabled={!settingsEditable || index === 0}
                  onClick={() => onMove(index, -1)}
                >
                  <ChevronUpIcon className="size-4" />
                </IconButton>
                <IconButton
                  type="button"
                  variant="secondary"
                  size="icon-sm"
                  label="Move down"
                  disabled={!settingsEditable || index === draftOrder.length - 1}
                  onClick={() => onMove(index, 1)}
                >
                  <ChevronDownIcon className="size-4" />
                </IconButton>
              </div>
            );
          })}
        </Stack>
        {!settingsEditable && (
          <Muted className="text-xs">
            Draft order is locked after the draft opens.
          </Muted>
        )}
        {(settingsEditable || timingEditable) && (
          <div className="flex justify-start">
            <IconButton
              type="button"
              label="Save draft settings"
              variant="primary"
              busy={settingsBusy}
              onClick={onSave}
            >
              <SaveIcon />
            </IconButton>
          </div>
        )}

        {settingsEditable && (
          <div className="flex flex-col gap-3 border-t border-line pt-3">
            <div>
              <h3 className="text-sm font-bold text-ink">Preassign</h3>
              <Muted className="mt-1 text-xs leading-snug">
                Optionally give managers clubs before the live draft. Preassigned clubs skip the
                draft and count toward that manager’s roster.
              </Muted>
            </div>
            <div
              className={
                showPreassignTools
                  ? "grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(6.5rem,8rem)] sm:items-start"
                  : undefined
              }
            >
              <div className="flex flex-col gap-1.5 text-sm font-semibold text-muted sm:items-start">
                <LabelRow>
                  Preassign mode
                  <FieldHelp label="Preassign mode">
                    <p className="mb-2">Whether clubs can be assigned before the live draft.</p>
                    <ul className="list-disc space-y-1 pl-4">
                      <li>
                        <strong className="text-ink">Off</strong> — no pre-draft assignments.
                      </li>
                      <li>
                        <strong className="text-ink">Optional</strong> — preassign is available;
                        each manager may have up to the configured number.
                      </li>
                      <li>
                        <strong className="text-ink">Required</strong> — every manager must have
                        exactly the configured number before the draft opens.
                      </li>
                    </ul>
                  </FieldHelp>
                </LabelRow>
                <ChoiceToggle
                  label="Preassign mode"
                  value={preassignMode}
                  disabled={settingsBusy}
                  options={
                    [
                      { id: "off", label: "Off" },
                      { id: "optional", label: "Optional" },
                      { id: "required", label: "Required" },
                    ] as const
                  }
                  onChange={onPreassignModeChange}
                />
              </div>
              {showPreassignTools && (
                <div className="flex flex-col gap-1.5">
                  <Label>
                    Per manager
                    <Input
                      type="number"
                      min={countMin}
                      step={1}
                      value={preassignCount}
                      disabled={settingsBusy}
                      onChange={(e) => {
                        const raw = Number(e.target.value);
                        if (!Number.isFinite(raw)) return;
                        const next = Math.max(countMin, Math.floor(raw));
                        onPreassignCountChange(next);
                      }}
                    />
                  </Label>
                  <Muted className="text-xs leading-snug">
                    {preassignMode === "required"
                      ? "Exact count required for every manager."
                      : "Max per manager (0 allowed)."}
                  </Muted>
                </div>
              )}
            </div>
            {showPreassignTools && (
              <form className="flex flex-col gap-3" onSubmit={onPreassign}>
                {multiPool ? (
                  <Label>
                    Competition
                    <PoolFilterSelect
                      name="pool"
                      pools={league.pools}
                      value={teamPool}
                      onChange={onTeamPool}
                    />
                  </Label>
                ) : (
                  league.pools[0] && (
                    <input type="hidden" name="pool" value={league.pools[0].id} />
                  )
                )}
                <Label>
                  Team
                  <Select name="member">
                    {league.members.map((m) => (
                      <option value={m.id} key={m.id}>
                        {managerOptionLabel(m)}
                      </option>
                    ))}
                  </Select>
                </Label>
                <Label>
                  Available club
                  <Select name="team" required key={teamPool || "all"}>
                    <option value="">Choose…</option>
                    {(teamPool
                      ? (poolTeams[teamPool] || []).map((t) => ({
                          ...t,
                          pool_id: teamPool,
                          pool_label:
                            league.pools.find((p) => p.id === teamPool)?.label ||
                            league.pools.find((p) => p.id === teamPool)?.key ||
                            "",
                        }))
                      : league.pools.flatMap((pool) =>
                          (poolTeams[pool.id] || []).map((t) => ({
                            ...t,
                            pool_id: pool.id,
                            pool_label: pool.label || pool.key,
                          })),
                        )
                    )
                      .filter((t) => t.available)
                      .sort((a, b) => a.name.localeCompare(b.name))
                      .map((t) => {
                        const encodePool = multiPool && !teamPool;
                        const value = encodePool ? `${t.pool_id}:${t.id}` : t.id;
                        const label = multiPool ? `${t.name} (${t.pool_label})` : t.name;
                        return (
                          <option value={value} key={`${t.pool_id}:${t.id}`}>
                            {label}
                          </option>
                        );
                      })}
                  </Select>
                </Label>
                <div className="flex justify-start">
                  <Button type="submit" variant="primary">
                    <UserPlusIcon className="size-4" />
                    Assign club
                  </Button>
                </div>
              </form>
            )}
          </div>
        )}
      </Stack>
    </Card>
  );
}
