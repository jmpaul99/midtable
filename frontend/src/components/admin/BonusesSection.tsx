"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import { formatNumber } from "@/lib/format";
import { humanizeKey } from "@/components/settings/types";
import type { Bonus, BonusTarget, League, Manager, MatchLogRow, PoolTeam, UUID } from "@/lib/types";
import { managerLabel } from "@/lib/types";
import { Empty, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { AwardIcon, BanIcon } from "@/components/ui/icons";
import { Autocomplete } from "@/components/ui/Autocomplete";
import { MatchAutocomplete } from "@/components/admin/MatchAutocomplete";
import { Card, Muted, Stack } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Input, Label } from "@/components/ui/Field";
import { cn } from "@/lib/cn";
import { BonusTypesListEditor } from "@/components/settings";
import type { BonusTypeRow } from "./useAdminLeagueData";

type Tab = "award" | "types" | "history";

const TARGETS: Array<{ id: BonusTarget; label: string }> = [
  { id: "team", label: "Team" },
  { id: "match", label: "Match" },
  { id: "manager", label: "Manager" },
];

function historyTargetLabel(b: Bonus): string {
  if (b.target === "manager" || (!b.team_id && b.display_name)) {
    return b.display_name || "Manager";
  }
  if (b.target === "match" || b.match_id) {
    const match = b.match_label || "Match";
    const team = b.team_name ? ` · ${b.team_name}` : "";
    const owner = b.display_name ? ` · ${b.display_name}` : "";
    return `${match}${team}${owner}`;
  }
  const team = b.team_name || b.team_id || "Team";
  const owner = b.display_name ? ` · ${b.display_name}` : "";
  return `${team}${owner}`;
}

export function BonusesSection({
  leagueId,
  bonusTypes,
  bonuses,
  allTeams,
  members = [],
  onAction,
  embedded = false,
}: {
  leagueId: UUID;
  bonusTypes: BonusTypeRow[];
  bonuses?: Bonus[];
  allTeams: Array<{ team: PoolTeam; pool: League["pools"][number] }>;
  members?: Manager[];
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

  const listItems = useMemo(
    () =>
      sortedTypes.map((t, i) => ({
        id: t.id,
        key: t.key,
        label: t.label,
        default_points: t.default_points,
        sort_order: t.sort_order ?? i + 1,
      })),
    [sortedTypes],
  );

  const [tab, setTab] = useState<Tab>("types");
  const [target, setTarget] = useState<BonusTarget>("team");
  const [awardTeamId, setAwardTeamId] = useState("");
  const [awardMatchId, setAwardMatchId] = useState("");
  const [selectedMatch, setSelectedMatch] = useState<MatchLogRow | null>(null);
  const [awardMemberId, setAwardMemberId] = useState("");
  const [awardTypeId, setAwardTypeId] = useState("");
  const [awardConfirmOpen, setAwardConfirmOpen] = useState(false);
  const [pendingRevokeId, setPendingRevokeId] = useState<UUID | null>(null);
  const pendingAwardForm = useRef<HTMLFormElement | null>(null);

  const teamOptions = useMemo(
    () =>
      allTeams.map(({ team, pool }) => ({
        value: team.id,
        label: `${team.name} · ${pool.label}`,
      })),
    [allTeams],
  );

  const matchTeamOptions = useMemo(() => {
    if (!selectedMatch) return [];
    return [
      {
        value: selectedMatch.home_team_id,
        label: `${selectedMatch.home_team_name} (Home)`,
      },
      {
        value: selectedMatch.away_team_id,
        label: `${selectedMatch.away_team_name} (Away)`,
      },
    ];
  }, [selectedMatch]);

  const memberOptions = useMemo(
    () =>
      [...members]
        .sort((a, b) => managerLabel(a).localeCompare(managerLabel(b)))
        .map((m) => ({
          value: m.id,
          label: managerLabel(m),
        })),
    [members],
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

  const awardReady =
    !!awardTypeId &&
    ((target === "team" && !!awardTeamId) ||
      (target === "match" && !!awardMatchId && !!awardTeamId) ||
      (target === "manager" && !!awardMemberId));

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "types", label: `Types (${sortedTypes.length})` },
    { id: "award", label: "Award" },
    { id: "history", label: `Awarded (${awardedCount})` },
  ];

  function resetAwardForm(form?: HTMLFormElement) {
    form?.reset();
    setAwardTeamId("");
    setAwardMatchId("");
    setSelectedMatch(null);
    setAwardMemberId("");
    setAwardTypeId("");
  }

  function onTargetChange(next: BonusTarget) {
    setTarget(next);
    setAwardTeamId("");
    setAwardMatchId("");
    setSelectedMatch(null);
    setAwardMemberId("");
  }

  function award(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!awardReady) return;
    pendingAwardForm.current = e.currentTarget;
    setAwardConfirmOpen(true);
  }

  async function confirmAward() {
    const form = pendingAwardForm.current;
    pendingAwardForm.current = null;
    setAwardConfirmOpen(false);
    if (!form) return;
    const f = new FormData(form);
    const notes = String(f.get("notes") || "").trim();
    const body: Record<string, unknown> = {
      target,
      bonus_type_id: awardTypeId,
      notes: notes || null,
    };
    if (target === "team") {
      body.team_id = awardTeamId;
    } else if (target === "match") {
      body.match_id = awardMatchId;
      body.team_id = awardTeamId;
    } else {
      body.member_id = awardMemberId;
    }
    await onAction(`/leagues/${leagueId}/manual-bonuses`, "POST", body);
    resetAwardForm(form);
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
              <div>
                <Muted className="mb-1 block text-[11px] font-bold uppercase tracking-wide">
                  Award to
                </Muted>
                <div
                  className="inline-flex w-fit max-w-full gap-0.5 rounded-md bg-surface-2 p-0.5"
                  role="radiogroup"
                  aria-label="Bonus target"
                >
                  {TARGETS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      role="radio"
                      aria-checked={target === t.id}
                      onClick={() => onTargetChange(t.id)}
                      className={cn(
                        "rounded px-2 py-1 text-[11px] font-bold transition sm:text-xs",
                        target === t.id
                          ? "bg-surface text-ink shadow-sm"
                          : "text-muted hover:text-ink",
                      )}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              {target === "team" && (
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
              )}

              {target === "match" && (
                <>
                  <Label>
                    Match
                    <MatchAutocomplete
                      leagueId={leagueId}
                      value={awardMatchId}
                      selectedMatch={selectedMatch}
                      onChange={(id, match) => {
                        setAwardMatchId(id);
                        setSelectedMatch(match);
                        setAwardTeamId("");
                      }}
                      required
                      placeholder="Search by club name…"
                    />
                  </Label>
                  <Label>
                    Team in match
                    <Autocomplete
                      value={awardTeamId}
                      onChange={setAwardTeamId}
                      options={matchTeamOptions}
                      required
                      disabled={!awardMatchId}
                      placeholder={
                        awardMatchId ? "Select home or away…" : "Pick a match first…"
                      }
                      emptyMessage="No teams available."
                    />
                  </Label>
                </>
              )}

              {target === "manager" && (
                <Label>
                  Manager
                  {memberOptions.length === 0 ? (
                    <Muted className="mt-1 block text-xs">
                      No managers in this league yet.
                    </Muted>
                  ) : (
                    <Autocomplete
                      value={awardMemberId}
                      onChange={setAwardMemberId}
                      options={memberOptions}
                      required
                      placeholder="Search managers…"
                      emptyMessage="No managers match."
                    />
                  )}
                </Label>
              )}

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
                  disabled={!awardReady}
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
          <BonusTypesListEditor
            value={listItems}
            onCreate={(item) =>
              onAction(`/leagues/${leagueId}/bonus-types`, "POST", item)
            }
            onUpdate={(id, patch) =>
              onAction(`/leagues/${leagueId}/bonus-types/${id}`, "PATCH", patch)
            }
            onDelete={(id) =>
              onAction(`/leagues/${leagueId}/bonus-types/${id}`, "DELETE")
            }
          />
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
                  sortedTypes.find((t) => t.key === b.bonus_type)?.label ||
                  humanizeKey(b.bonus_type);
                const targetLabel =
                  b.target === "manager"
                    ? "Manager"
                    : b.target === "match"
                      ? "Match"
                      : "Team";
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
                        {targetLabel} · {historyTargetLabel(b)}
                        {b.reason ? ` · ${b.reason}` : ""}
                      </Muted>
                    </div>
                    <IconButton
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      label="Revoke bonus"
                      className="text-danger hover:bg-danger/10 hover:text-danger"
                      onClick={() => setPendingRevokeId(b.id)}
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

      <ConfirmDialog
        open={awardConfirmOpen}
        title="Award this bonus?"
        description="Award this bonus using the configured points?"
        confirmLabel="Award bonus"
        cancelLabel="Cancel"
        tone="warning"
        onCancel={() => {
          pendingAwardForm.current = null;
          setAwardConfirmOpen(false);
        }}
        onConfirm={() => void confirmAward()}
      />
      <ConfirmDialog
        open={Boolean(pendingRevokeId)}
        title="Revoke this bonus?"
        description="Revoke this awarded bonus?"
        confirmLabel="Revoke"
        cancelLabel="Cancel"
        tone="danger"
        onCancel={() => setPendingRevokeId(null)}
        onConfirm={() => {
          if (pendingRevokeId) {
            onAction(`/leagues/${leagueId}/manual-bonuses/${pendingRevokeId}`, "DELETE");
          }
          setPendingRevokeId(null);
        }}
      />
    </Stack>
  );

  if (embedded) return body;
  return <Card>{body}</Card>;
}
