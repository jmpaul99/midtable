"use client";

import { useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { Manager, RosterRow, UUID } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import { Card, Muted, RankBadge, Stack } from "@/components/ui/Card";
import {
  compareRosterClubs,
  effectiveRosterClubOrder,
  type RosterClubOrder,
} from "@/lib/rosterClubOrder";
import { TeamCrest } from "./TeamCrest";
import { TeamLink } from "./TeamLink";
import { ManagerLink } from "./ManagerLink";
import { TeamNameEditor } from "./TeamNameEditor";
import { StagePointsBreakdown } from "./StagePointsBreakdown";

function FormDots({ form }: { form?: string[] | null }) {
  if (!form?.length) return null;
  return (
    <span className="inline-flex shrink-0 items-center gap-0.5" aria-label={`Form ${form.join("")}`}>
      {form.map((letter, i) => (
        <span
          key={`${letter}-${i}`}
          className={
            letter === "W"
              ? "text-xs font-extrabold leading-none text-emerald-700"
              : letter === "D"
                ? "text-xs font-extrabold leading-none text-amber-700"
                : "text-xs font-extrabold leading-none text-rose-700"
          }
        >
          {letter}
        </span>
      ))}
    </span>
  );
}

export function RosterGrid({
  leagueId,
  members = [],
  currentMemberId,
  onTeamNameSaved,
  leagueStatus,
  rosterClubOrder = "draft",
}: {
  leagueId: UUID;
  members?: Manager[];
  currentMemberId?: UUID | null;
  onTeamNameSaved?: () => void;
  leagueStatus?: string;
  rosterClubOrder?: RosterClubOrder;
}) {
  const clubOrder = effectiveRosterClubOrder(leagueStatus, rosterClubOrder);
  const [rows, setRows] = useState<RosterRow[]>();
  const [error, setError] = useState("");

  const membersById = useMemo(() => {
    const map = new Map<UUID, Manager>();
    for (const m of members) map.set(m.id, m);
    return map;
  }, [members]);

  useEffect(() => {
    api<RosterRow[]>(`/leagues/${leagueId}/rosters`)
      .then(setRows)
      .catch((e) => setError(errorMessage(e)));
  }, [leagueId]);

  const draftOrder = useMemo(() => {
    const order = new Map<UUID, number>();
    [...members]
      .sort((a, b) => (a.draft_slot ?? 999) - (b.draft_slot ?? 999))
      .forEach((m, i) => order.set(m.id, m.draft_slot ?? i + 1));
    return order;
  }, [members]);

  const grouped = useMemo(() => {
    const byMember = new Map<UUID, RosterRow[]>();
    for (const row of rows || []) {
      const existing = byMember.get(row.member_id);
      if (existing) existing.push(row);
      else byMember.set(row.member_id, [row]);
    }
    return [...byMember.entries()]
      .map(([memberId, slots]) => {
        const member = membersById.get(memberId);
        const teamName = managerLabel(member, slots[0]?.display_name || "Manager");
        const displayName = member?.display_name?.trim() || null;
        const sample = slots[0];
        const clubPoints = slots
          .filter((s) => s.team_id)
          .map((s) => Number(s.points || 0));
        const maxClub = Math.max(0, ...clubPoints);
        return {
          memberId,
          member,
          teamName,
          displayName,
          draftSlot: draftOrder.get(memberId) ?? 999,
          rank: sample?.rank ?? null,
          totalPoints: sample?.member_total_points ?? 0,
          ppg: sample?.member_points_per_game ?? 0,
          wins: sample?.member_wins ?? 0,
          draws: sample?.member_draws ?? 0,
          losses: sample?.member_losses ?? 0,
          maxClub,
          slots: [...slots].sort((a, b) => compareRosterClubs(a, b, clubOrder)),
        };
      })
      .sort(
        (a, b) =>
          (a.rank ?? 999) - (b.rank ?? 999) ||
          a.draftSlot - b.draftSlot ||
          a.teamName.localeCompare(b.teamName),
      );
  }, [rows, draftOrder, membersById, clubOrder]);

  if (error) return <ErrorState error={error} />;
  if (!rows) return <Loading label="Loading rosters" />;
  if (!rows.length) return <Empty title="No roster slots found" />;

  return (
    <div className="animate-in grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2 xl:grid-cols-3">
      {grouped.map((group) => {
        const isMine = Boolean(currentMemberId && group.memberId === currentMemberId);
        return (
          <Card key={group.memberId} className="min-w-0 overflow-hidden">
            <div className="mb-3 flex items-start gap-2.5 sm:gap-3">
              {group.rank != null && (
                <RankBadge value={group.rank} first={group.rank === 1} />
              )}
              <div className="min-w-0 flex-1">
                <TeamNameEditor
                  leagueId={leagueId}
                  memberId={group.memberId}
                  teamName={group.member?.team_name?.trim() || group.teamName}
                  displayName={group.displayName}
                  canEdit={isMine}
                  titleClassName="text-base"
                  titleContent={
                    <ManagerLink leagueId={leagueId} managerId={group.memberId}>
                      {group.teamName}
                    </ManagerLink>
                  }
                  onSaved={() => onTeamNameSaved?.()}
                />
                <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm tabular-nums text-muted">
                  <span className="font-semibold text-ink">
                    {formatNumber(group.totalPoints)} pts
                  </span>
                  <span>{formatNumber(group.ppg)} PPG</span>
                  <span>
                    {group.wins}-{group.draws}-{group.losses}
                  </span>
                </div>
              </div>
            </div>
            <Stack gap="sm">
              {group.slots.map((r) => {
                const pts = Number(r.points || 0);
                const share =
                  group.maxClub > 0 && r.team_id ? Math.round((pts / group.maxClub) * 100) : 0;
                return (
                  <div
                    className="min-w-0 rounded-xl border border-line bg-surface-2/50 p-2.5 sm:p-3"
                    key={`${r.member_id}-${r.pool_id}-${r.slot_number}`}
                  >
                    <div className="flex items-start gap-2.5 sm:items-center sm:gap-3">
                      <TeamCrest
                        name={r.team_name}
                        crestUrl={r.crest_url}
                        size="md"
                        className="mt-0.5 shrink-0 sm:mt-0"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <strong className="min-w-0 truncate text-sm sm:text-base">
                            {r.team_id && r.team_name ? (
                              <TeamLink leagueId={leagueId} teamId={r.team_id}>
                                {r.team_name}
                              </TeamLink>
                            ) : (
                              "Open slot"
                            )}
                          </strong>
                          {r.team_id && (
                            <div className="shrink-0 text-right leading-none">
                              <div className="font-display text-base font-extrabold tabular-nums sm:text-lg">
                                {formatNumber(pts)}
                              </div>
                            </div>
                          )}
                        </div>
                        <Muted className="mt-0.5 truncate text-xs sm:text-sm">
                          {r.pool_name}
                          {r.draft_pick_number != null
                            ? ` · Pick #${r.draft_pick_number}`
                            : r.acquired_via
                              ? ` · ${r.acquired_via.replaceAll("_", " ")}`
                              : " · Awaiting draft"}
                        </Muted>
                        {r.team_id && (
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                            <span className="text-xs tabular-nums text-muted">
                              {r.games_played ?? 0} GP ·{" "}
                              {formatNumber(Number(r.points_per_game || 0))} PPG
                            </span>
                            <FormDots form={r.form} />
                          </div>
                        )}
                        {r.team_id && (
                          <StagePointsBreakdown
                            pointsByStage={r.points_by_stage}
                            compact
                          />
                        )}
                      </div>
                    </div>
                    {r.team_id && group.maxClub > 0 && (
                      <div className="mt-2 h-1 overflow-hidden rounded-full bg-line sm:h-1.5">
                        <div
                          className="h-full rounded-full bg-brand/80"
                          style={{ width: `${share}%` }}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </Stack>
          </Card>
        );
      })}
    </div>
  );
}
