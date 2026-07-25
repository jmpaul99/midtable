"use client";

import { FormEvent, useState } from "react";
import { formatDate } from "@/lib/format";
import type { League, Readiness, SyncStatus } from "@/lib/types";
import { MatchLog } from "@/components/league/MatchLog";
import { ErrorState, Loading, Status, StatusBanner } from "@/components/ui/State";
import { IconButton } from "@/components/ui/IconButton";
import { DownloadIcon, RefreshIcon } from "@/components/ui/icons";
import { Card, Muted, Row, Stack } from "@/components/ui/Card";
import { cn } from "@/lib/cn";
import { LeagueMetaSettingsSection } from "./LeagueMetaSettingsSection";
import { LeagueSettingsSection } from "./LeagueSettingsSection";
import { RankingIngest } from "./RankingIngest";
import { SeasonActionsSection } from "./SeasonActionsSection";
import { useAdminLeagueData } from "./useAdminLeagueData";

const SECTIONS = [
  { id: "league", label: "League" },
  { id: "settings", label: "Scoring" },
  { id: "sync", label: "Sync" },
  { id: "rankings", label: "Rankings" },
  { id: "matches", label: "Matches" },
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
    bonuses,
    bonusTypes,
    sync,
    poolTeams,
    readiness,
    error,
    message,
    setMessage,
    load,
    action,
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
    const out = await action(`/leagues/${league.id}/bootstrap-teams`, "POST", {
      pool_provider_params,
    });
    if (!out) {
      throw new Error("Failed to reload teams from the provider.");
    }
    const pools = Array.isArray(out.pools) ? (out.pools as Array<Record<string, unknown>>) : [];
    const poolErrors = pools
      .filter((p) => typeof p.error === "string")
      .map((p) => `${p.pool_key}: ${p.error}`);
    const base = `Teams loaded: ${out.linked ?? 0} linked, ${out.created_teams ?? 0} created, ${out.skipped_existing ?? 0} already present.`;
    setMessage(poolErrors.length ? `${base} Issues — ${poolErrors.join("; ")}` : base);
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
      {message && (
        <StatusBanner className="break-all font-mono text-xs sm:text-sm">{message}</StatusBanner>
      )}

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
          atOrOverCap={atOrOverCap}
          maxMembers={maxMembers}
          onInvite={invite}
          onResendInvite={(id) =>
            action(`/leagues/${league.id}/invites/${id}/resend`, "POST")
          }
          onRevoke={(id) => action(`/leagues/${league.id}/invites/${id}`, "DELETE")}
          onJoinLinkUpdate={(body) =>
            action(`/leagues/${league.id}/join-link`, "POST", body)
          }
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

      <Card id="admin-matches">
        <Stack>
          <h2>Recent match log</h2>
          <MatchLog leagueId={league.id} limit={20} compact />
        </Stack>
      </Card>

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
  const checks = readiness?.checks?.length
    ? readiness.checks
    : [
        ...(readiness?.errors || []).map((detail, i) => ({
          key: `error-${i}`,
          label: detail,
          status: "error" as const,
          detail: null,
        })),
        ...(readiness?.warnings || []).map((detail, i) => ({
          key: `warning-${i}`,
          label: detail,
          status: "warning" as const,
          detail: null,
        })),
      ];
  const blocking = checks.filter((c) => c.status === "error");
  const caution = checks.filter((c) => c.status === "warning");

  return (
    <Card>
      <Stack>
        <div>
          <h2>Readiness &amp; Sync</h2>
          <Muted className="mt-1 text-sm">
            Checklist of every setup and sync gate. Errors block readiness; warnings should be fixed
            before relying on live scores. Clubs reload when you save competitions that were added,
            removed, or had their season year changed.
          </Muted>
        </div>

        <Stack>
          {needsTeamLoad && (
            <StatusBanner>
              Competitions are empty. Save competitions in League settings to load clubs before
              drafting or preassigning.
            </StatusBanner>
          )}

          {readiness ? (
            <>
              <StatusBanner tone={readiness.ready ? "success" : "error"}>
                <strong>
                  {readiness.ready
                    ? caution.length
                      ? "Ready with warnings"
                      : "Ready to sync"
                    : "Not ready"}
                </strong>
                <div className="mt-1 text-sm">
                  {readiness.ready
                    ? caution.length
                      ? `${caution.length} warning(s) below — sync may skip some competitions.`
                      : "All blocking checks passed."
                    : `${blocking.length} issue(s) to fix before this league is ready.`}
                </div>
              </StatusBanner>

              <details className="group rounded-xl border border-line bg-surface-2/40">
                <summary className="cursor-pointer list-none px-3 py-2.5 text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
                  <span className="flex items-center justify-between gap-2">
                    <span>
                      Pre-sync checks
                      <Muted className="ml-1.5 font-normal">
                        ({checks.length}
                        {blocking.length
                          ? ` · ${blocking.length} error${blocking.length === 1 ? "" : "s"}`
                          : ""}
                        {caution.length
                          ? ` · ${caution.length} warning${caution.length === 1 ? "" : "s"}`
                          : ""}
                        )
                      </Muted>
                    </span>
                    <span className="text-muted transition group-open:rotate-180" aria-hidden>
                      ▾
                    </span>
                  </span>
                </summary>
                <ul className="flex max-h-48 flex-col gap-2 overflow-y-auto overscroll-contain border-t border-line p-3">
                  {checks.map((c) => (
                    <li key={c.key} className="flex items-start gap-2.5 text-sm">
                      <span
                        className={cn(
                          "mt-0.5 grid size-5 shrink-0 place-items-center rounded-md text-xs font-extrabold",
                          c.status === "ok" && "bg-brand/15 text-brand",
                          c.status === "error" && "bg-danger/15 text-danger",
                          c.status === "warning" && "bg-warning/15 text-warning",
                        )}
                        aria-hidden
                      >
                        {c.status === "ok" ? "✓" : c.status === "error" ? "!" : "·"}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="font-semibold text-ink">{c.label}</div>
                        {c.detail && <Muted className="text-xs">{c.detail}</Muted>}
                      </div>
                    </li>
                  ))}
                </ul>
              </details>
            </>
          ) : (
            <Loading label="Checking readiness" />
          )}

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
                  onClick={() => {
                    if (
                      confirm(
                        "Pull latest fixtures and results from football-data.org and score finished matches?",
                      )
                    ) {
                      onSync();
                    }
                  }}
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
                  onClick={() => {
                    if (
                      confirm(
                        "Recompute scoring for all finished matches? This rewrites scoring events from current results.",
                      )
                    ) {
                      onRecompute();
                    }
                  }}
                >
                  <RefreshIcon />
                </IconButton>
              </div>
            </div>
          </div>

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
