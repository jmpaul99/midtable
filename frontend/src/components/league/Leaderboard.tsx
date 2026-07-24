"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, formatNumber } from "@/lib/api";
import type { League, PhaseMetadata, Standing, StandingsResponse } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { Empty, ErrorState, Loading } from "@/components/ui/State";
import { Button } from "@/components/ui/Button";
import { Card, Eyebrow, Muted, RankBadge, Stack } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { managerHref } from "./ManagerLink";

const SEASON_KEY = "";

function uniquePhases(league: League) {
  return league.phases.filter(
    (phase, index, all) => all.findIndex((item) => item.key === phase.key) === index,
  );
}

function formatMatchweekRange(range: number[] | null | undefined): string | null {
  if (!range || range.length < 2) return null;
  return `Matchweeks ${range[0]}–${range[1]}`;
}

function formatStages(stages: string[] | null | undefined): string | null {
  if (!stages?.length) return null;
  return `Stages: ${stages.map((s) => s.replaceAll("_", " ")).join(", ")}`;
}

function phaseBonusTypes(league: League, phaseKey: string): string[] {
  const fromMeta = league.phases.find((p) => p.key === phaseKey)?.include_bonus_types;
  if (fromMeta?.length) return fromMeta;
  const raw = league.leaderboard_phases?.find(
    (p) => typeof p === "object" && p !== null && (p as { key?: string }).key === phaseKey,
  ) as { include_bonus_types?: string[] } | undefined;
  return raw?.include_bonus_types ?? [];
}

function phaseScopeParts(
  league: League,
  phaseKey: string,
  meta?: PhaseMetadata,
): string[] {
  const isSeason = phaseKey === SEASON_KEY;
  const selected = isSeason ? undefined : league.phases.find((p) => p.key === phaseKey);
  const source = meta ?? selected;
  const parts: string[] = [];

  if (isSeason) {
    parts.push("Full season");
  } else {
    const scope =
      formatMatchweekRange(source?.matchweek_range ?? selected?.matchweek_range) ||
      formatStages(source?.stage_in ?? selected?.stage_in);
    if (scope) parts.push(scope);
  }

  const bonuses = isSeason
    ? []
    : meta?.include_bonus_types?.length
      ? meta.include_bonus_types
      : phaseBonusTypes(league, phaseKey);
  if (bonuses.length) {
    parts.push(`Bonuses: ${bonuses.join(", ")}`);
  }

  return parts;
}

function phaseProgressParts(meta?: PhaseMetadata): string[] {
  if (!meta || meta.matching_matches == null) return [];
  if (meta.matching_matches === 0) return ["No matching fixtures"];
  const parts: string[] = [];
  if (meta.is_final) parts.push("Final");
  else if (meta.remaining_matches != null) parts.push(`${meta.remaining_matches} remaining`);
  if (meta.finished_matches != null) {
    parts.push(`${meta.finished_matches}/${meta.matching_matches} finished`);
  }
  return parts;
}

function rowLabels(league: League, row: Standing) {
  const member = league.members.find((m) => m.id === row.member_id);
  const teamName =
    row.team_name?.trim() ||
    member?.team_name?.trim() ||
    managerLabel(member, row.display_name);
  const ownerName =
    row.owner_name?.trim() ||
    member?.display_name?.trim() ||
    member?.email ||
    null;
  return { teamName, ownerName };
}

export function Leaderboard({ league }: { league: League }) {
  const router = useRouter();
  const [phase, setPhase] = useState(SEASON_KEY);
  const [result, setResult] = useState<StandingsResponse>();
  const [error, setError] = useState("");

  useEffect(() => {
    setResult(undefined);
    setError("");
    const path =
      phase === SEASON_KEY
        ? `/leagues/${league.id}/standings`
        : `/leagues/${league.id}/standings?phase=${encodeURIComponent(phase)}`;
    api<StandingsResponse>(path)
      .then(setResult)
      .catch((e) => setError(errorMessage(e)));
  }, [league.id, phase]);

  const rows = result?.entries;
  const phases = uniquePhases(league);
  const infoParts = [
    ...phaseScopeParts(league, phase, result?.phase),
    ...phaseProgressParts(result?.phase),
  ];

  return (
    <Card className="animate-in">
      <Stack>
        <div>
          <Eyebrow>Leaderboard</Eyebrow>
          <h2>{result?.phase.name || (phase === SEASON_KEY ? "Season" : phase)}</h2>
          {infoParts.length > 0 && (
            <Muted className="mt-1">{infoParts.join(" · ")}</Muted>
          )}
        </div>

        {phases.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1">
            <Button
              type="button"
              variant={phase === SEASON_KEY ? "primary" : "secondary"}
              onClick={() => setPhase(SEASON_KEY)}
              className="shrink-0"
              title="Full season standings"
            >
              Season
            </Button>
            {phases.map((p) => {
              const tip = phaseScopeParts(league, p.key).join(" · ") || p.name;
              return (
                <Button
                  type="button"
                  key={p.key}
                  variant={phase === p.key ? "primary" : "secondary"}
                  onClick={() => setPhase(p.key)}
                  className="shrink-0"
                  title={tip}
                >
                  {p.name}
                </Button>
              );
            })}
          </div>
        )}

        {error ? (
          <ErrorState error={error} />
        ) : !rows ? (
          <Loading label="Loading standings" />
        ) : !rows.length ? (
          <Empty title="No scored matches yet" />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full min-w-[20rem] text-left text-sm">
              <thead className="border-b border-line text-xs font-bold uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-3 py-2.5 font-bold">#</th>
                  <th className="px-3 py-2.5 font-bold">Team</th>
                  <th className="px-3 py-2.5 font-bold">Owner</th>
                  <th className="px-3 py-2.5 text-right font-bold">Pts</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const tied = i > 0 && rows[i - 1].rank === r.rank;
                  const { teamName, ownerName } = rowLabels(league, r);
                  const href = managerHref(league.id, r.member_id);
                  return (
                    <tr
                      key={r.member_id}
                      role={href ? "link" : undefined}
                      tabIndex={href ? 0 : undefined}
                      onClick={() => {
                        if (href) router.push(href);
                      }}
                      onKeyDown={(e) => {
                        if (!href) return;
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          router.push(href);
                        }
                      }}
                      className={cn(
                        "border-b border-line last:border-0 transition",
                        r.rank === 1 && "bg-brand/10",
                        href &&
                          "group cursor-pointer hover:bg-brand/5 focus-visible:bg-brand/5 focus-visible:outline-none",
                      )}
                    >
                      <td className="px-3 py-3 align-middle">
                        <div className="flex items-center gap-1.5">
                          <RankBadge value={r.rank} first={r.rank === 1} />
                          {tied && <Muted className="text-xs">T</Muted>}
                        </div>
                      </td>
                      <td className="max-w-[8rem] truncate px-3 py-3 align-middle sm:max-w-[14rem]">
                        <span className="font-semibold text-ink transition group-hover:text-brand">
                          {teamName}
                        </span>
                      </td>
                      <td className="max-w-[7rem] truncate px-3 py-3 align-middle text-muted sm:max-w-[10rem]">
                        {ownerName || "—"}
                      </td>
                      <td className="px-3 py-3 text-right align-middle">
                        <span className="font-display text-lg font-extrabold tabular-nums">
                          {formatNumber(r.total_points)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Stack>
    </Card>
  );
}
