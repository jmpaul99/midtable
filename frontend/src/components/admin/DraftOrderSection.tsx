"use client";

import { FormEvent } from "react";
import type { League, PoolTeam, UUID } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { IconButton } from "@/components/ui/IconButton";
import { ChevronDownIcon, ChevronUpIcon, SaveIcon, UserPlusIcon } from "@/components/ui/icons";
import { Card, Muted, RankBadge, Stack } from "@/components/ui/Card";
import { Label, Select } from "@/components/ui/Field";

export function DraftOrderSection({
  league,
  draftOrder,
  teamPool,
  poolTeams,
  onMove,
  onTeamPool,
  onSaveOrder,
  onPreassign,
}: {
  league: League;
  draftOrder: UUID[];
  teamPool: string;
  poolTeams: Record<string, PoolTeam[]>;
  onMove: (index: number, direction: -1 | 1) => void;
  onTeamPool: (id: string) => void;
  onSaveOrder: () => void;
  onPreassign: (e: FormEvent<HTMLFormElement>) => void;
}) {
  const multiPool = league.pools.length > 1;
  const preassignsByMember = new Map<UUID, string[]>();
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

  return (
    <Card>
      <Stack>
        <h2>Draft order &amp; preassigns</h2>
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
                  {preassigned?.length ? (
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
      </Stack>
    </Card>
  );
}
