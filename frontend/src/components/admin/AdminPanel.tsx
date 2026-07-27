"use client";

import { FormEvent, useState } from "react";
import { formatDate } from "@/lib/format";
import type { League, Readiness, SyncStatus } from "@/lib/types";
import { ErrorState, Status, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { DownloadIcon, RefreshIcon } from "@/components/ui/icons";
import { Card, Muted, Row, Stack } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { cn } from "@/lib/cn";
import { ReadinessChecklist } from "@/components/ReadinessChecklist";
import { LeagueMetaSettingsSection } from "./LeagueMetaSettingsSection";
import { LeagueSettingsSection } from "./LeagueSettingsSection";
import { RankingIngest } from "./RankingIngest";
import { SeasonActionsSection } from "./SeasonActionsSection";
import { useAdminLeagueData } from "./useAdminLeagueData";

const SYNC_WARNING =
  "Pull latest fixtures and results from football-data.org and score finished matches?";

const RECOMPUTE_WARNING =
  "Recompute scoring for all finished matches? This rewrites scoring events from current results.";

const SECTIONS = [
  { id: "league", label: "League" },
  { id: "settings", label: "Scoring" },
  { id: "sync", label: "Sync" },
  { id: "rankings", label: "Rankings" },
  { id: "season", label: "Season" },
] as const;

function usesFixedRankingList(league: League): boolean {
  const rules = league.upset_rules;
  if (!rules || typeof rules !== "object") return false;
  return rules.rank_source === "fixed_ranking_at_event_start";
}

export function AdminPanel({
  league,
  onLeagueChange,
}: {
  league: League;
  onLeagueChange?: () => void;
}) {
  const {
    invites,
    joinLink,
    joinLinkBusy,
    bonuses,
    bonusTypes,
    sync,
    poolTeams,
    readiness,
    error,
    load,
    action,
    updateJoinLink,
    toast,
  } = useAdminLeagueData(league, onLeagueChange);

  const [activeSection, setActiveSection] = useState<string>("league");

  const maxMembers =
    league.max_members ??
    (typeof league.settings?.max_members === "number" ? league.settings.max_members : null);
  const atOrOverCap = maxMembers != null && league.members.length >= maxMembers;
  const showRankings = usesFixedRankingList(league);
  const needsTeamLoad =
    league.pools.length > 0 &&
    league.pools.some((p) => (poolTeams[p.id] || []).length === 0);
  const navSections = SECTIONS.filter((s) => {
    if (s.id === "rankings" && !showRankings) return false;
    return true;
  });

  async function invite(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const form = e.currentTarget;
    const out = await action(`/leagues/${league.id}/invites`, "POST", {
      email: f.get("email"),
      is_commissioner: f.get("commissioner") === "on",
    });
    if (out) form.reset();
  }

  async function loadTeams(
    pool_provider_params: Array<{ key: string; competition_code: string; season_year: number }>,
  ) {
    const out = await action(
      `/leagues/${league.id}/bootstrap-teams`,
      "POST",
      {
        pool_provider_params,
      },
      { quiet: true },
    );
    if (!out) {
      throw new Error("Failed to reload teams from the provider.");
    }
    const pools = Array.isArray(out.pools) ? (out.pools as Array<Record<string, unknown>>) : [];
    const competitionErrors = pools
      .filter((p) => typeof p.error === "string")
      .map((p) => {
        const name = String(p.label || p.pool_key || "competition");
        return `${name}: ${p.error}`;
      });
    const base = `Teams loaded: ${out.linked ?? 0} linked, ${out.created_teams ?? 0} created, ${out.skipped_existing ?? 0} already present.`;
    const text = competitionErrors.length
      ? `${base} Issues — ${competitionErrors.join("; ")}`
      : base;
    toast({
      message: text,
      tone: competitionErrors.length ? "error" : "success",
      durationMs: null,
      dismissible: true,
    });
  }

  const allTeams = league.pools.flatMap((pool) =>
    (poolTeams[pool.id] || []).map((team) => ({ team, pool })),
  );

  const teamCounts = Object.fromEntries(
    Object.entries(poolTeams).map(([id, teams]) => [id, teams.length]),
  );

  return (
    <Stack gap="md" className="animate-in">
      {error && <ErrorState error={error} retry={load} />}

      <nav
        className="sticky top-[calc(3.5rem+env(safe-area-inset-top))] z-20 -mx-1 flex gap-1 overflow-x-auto bg-bg/90 px-1 py-2 backdrop-blur-md sm:top-[calc(4rem+env(safe-area-inset-top))]"
        aria-label="Commissioner sections"
      >
        {navSections.map((s) => (
          <a
            key={s.id}
            href={`#admin-${s.id}`}
            onClick={() => setActiveSection(s.id)}
            className={cn(
              "inline-flex min-h-11 shrink-0 items-center rounded-full border px-3.5 py-2 text-xs font-bold transition",
              activeSection === s.id
                ? "border-brand bg-brand/10 text-brand"
                : "border-line bg-surface text-muted hover:text-ink",
            )}
          >
            {s.label}
          </a>
        ))}
      </nav>

      <details id="admin-league" open className="group">
        <summary className="mb-2 cursor-pointer list-none font-display text-lg font-extrabold [&::-webkit-details-marker]:hidden">
          League settings
        </summary>
        <LeagueMetaSettingsSection
          league={league}
          teamCounts={teamCounts}
          bonusTypeOptions={bonusTypes.map((b) => ({
            value: b.key,
            label: b.label || b.key,
          }))}
          invites={invites}
          joinLink={joinLink}
          joinLinkBusy={joinLinkBusy}
          atOrOverCap={atOrOverCap}
          maxMembers={maxMembers}
          onInvite={invite}
          onResendInvite={(id) =>
            action(`/leagues/${league.id}/invites/${id}/resend`, "POST")
          }
          onRevoke={(id) => action(`/leagues/${league.id}/invites/${id}`, "DELETE")}
          onJoinLinkUpdate={(body) => updateJoinLink(body)}
          onToggleCommissioner={(memberId, isCommissioner) =>
            action(`/leagues/${league.id}/members/${memberId}`, "PATCH", {
              is_commissioner: isCommissioner,
            })
          }
          onRemove={(memberId) =>
            action(`/leagues/${league.id}/members/${memberId}`, "DELETE")
          }
          onSaved={onLeagueChange}
          onReloadTeams={loadTeams}
        />
      </details>

      <details id="admin-settings" open className="group">
        <summary className="mb-2 cursor-pointer list-none font-display text-lg font-extrabold [&::-webkit-details-marker]:hidden">
          Scoring settings
        </summary>
        <LeagueSettingsSection
          league={league}
          bonusTypes={bonusTypes}
          bonuses={bonuses}
          allTeams={allTeams}
          members={league.members}
          onAction={action}
          onSaved={onLeagueChange}
        />
      </details>

      <div id="admin-sync">
        <SyncReadinessSection
          readiness={readiness}
          sync={sync}
          needsTeamLoad={needsTeamLoad}
          onSync={() => action(`/leagues/${league.id}/sync`, "POST")}
          onRecompute={() => action(`/leagues/${league.id}/recompute`, "POST")}
        />
      </div>

      {showRankings && (
        <div id="admin-rankings">
          <RankingIngest leagueId={league.id} />
        </div>
      )}

      <details id="admin-season" open className="group">
        <summary className="mb-2 cursor-pointer list-none font-display text-lg font-extrabold [&::-webkit-details-marker]:hidden">
          Season actions
        </summary>
        <SeasonActionsSection league={league} onSaved={onLeagueChange} />
      </details>
    </Stack>
  );
}

function SyncReadinessSection({
  readiness,
  sync,
  needsTeamLoad,
  onSync,
  onRecompute,
}: {
  readiness?: Readiness;
  sync?: SyncStatus[];
  needsTeamLoad: boolean;
  onSync: () => void;
  onRecompute: () => void;
}) {
  const [syncConfirmOpen, setSyncConfirmOpen] = useState(false);
  const [recomputeConfirmOpen, setRecomputeConfirmOpen] = useState(false);

  return (
    <Card>
      <Stack>
        <div>
          <h2>Readiness &amp; Sync</h2>
          <Muted className="mt-1 text-sm">
            Competition and provider checks for fixture sync. Errors mean Sync will skip or find
            nothing to pull. Manager roster and draft order are not required here — use the Draft
            board for those. Clubs reload when you save competitions that were added, removed, or
            had their season year changed.
          </Muted>
        </div>

        <Stack>
          {needsTeamLoad && (
            <StatusBanner>
              Competitions are empty. Save competitions in League settings to load clubs before
              drafting or preassigning.
            </StatusBanner>
          )}

          <ReadinessChecklist
            readiness={readiness}
            readyLabel="Ready to sync"
            readyWithWarningsDetail="warning(s) below — sync may skip some competitions."
            checksSummaryLabel="Sync checks"
          />

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col rounded-xl border border-line bg-surface-2/40 p-3">
              <strong className="text-sm">Sync now</strong>
              <Muted className="mt-1 grow text-xs">
                Pulls fixtures and results from football-data.org for every scoring competition that
                has a competition code and season year, then scores newly finished matches. It does
                not load clubs — save competitions in League settings for that.
              </Muted>
              <div className="mt-3 flex justify-start">
                <IconButton
                  type="button"
                  variant="secondary"
                  label="Sync fixtures & scores"
                  onClick={() => setSyncConfirmOpen(true)}
                >
                  <DownloadIcon />
                </IconButton>
              </div>
            </div>

            <div className="flex flex-col rounded-xl border border-line bg-surface-2/40 p-3">
              <strong className="text-sm">Recompute scores</strong>
              <Muted className="mt-1 grow text-xs">
                Rebuilds scoring events for all finished matches already in the database using
                current rules — no provider call.
              </Muted>
              <div className="mt-3 flex justify-start">
                <IconButton
                  type="button"
                  variant="secondary"
                  label="Recompute scores"
                  onClick={() => setRecomputeConfirmOpen(true)}
                >
                  <RefreshIcon />
                </IconButton>
              </div>
            </div>
          </div>

          <ConfirmDialog
            open={syncConfirmOpen}
            title="Sync fixtures & scores?"
            description={SYNC_WARNING}
            confirmLabel="Sync now"
            cancelLabel="Cancel"
            tone="warning"
            onCancel={() => setSyncConfirmOpen(false)}
            onConfirm={() => {
              setSyncConfirmOpen(false);
              onSync();
            }}
          />
          <ConfirmDialog
            open={recomputeConfirmOpen}
            title="Recompute scores?"
            description={RECOMPUTE_WARNING}
            confirmLabel="Recompute"
            cancelLabel="Cancel"
            tone="warning"
            onCancel={() => setRecomputeConfirmOpen(false)}
            onConfirm={() => {
              setRecomputeConfirmOpen(false);
              onRecompute();
            }}
          />

          {sync?.map((s) => (
            <div className="rounded-xl border border-line bg-surface-2/50 p-3" key={s.id}>
              <Row between>
                <strong>{s.provider || s.resource_type || "sync"}</strong>
                <Status value={s.status} />
              </Row>
              <Muted className="mt-1 text-xs">
                Last success {formatDate(s.last_success_at)} · quota{" "}
                {s.rate_limit_remaining ?? "—"}
              </Muted>
              {s.last_error && (
                <StatusBanner tone="error" className="mt-2">
                  {s.last_error}
                </StatusBanner>
              )}
            </div>
          ))}
        </Stack>
      </Stack>
    </Card>
  );
}
