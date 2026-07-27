"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type {
  Bonus,
  Invite,
  JoinLink,
  LatestLeagueJobs,
  League,
  LeagueJob,
  PoolTeam,
  Readiness,
  UUID,
} from "@/lib/types";
import { useToast } from "@/components/ui/ToastProvider";

export interface BonusTypeRow {
  id: UUID;
  key: string;
  label: string;
  default_points: number;
  sort_order?: number;
  include_in_phases?: string[];
}

const JOB_POLL_MS = 2500;
const ACTIVE_JOB = new Set(["pending", "running"]);

function isActiveJob(job: LeagueJob | null | undefined): boolean {
  return !!job && ACTIVE_JOB.has(job.status);
}

export function useAdminLeagueData(league: League, onLeagueChange?: () => void) {
  const { toast } = useToast();
  const [invites, setInvites] = useState<Invite[]>();
  const [joinLink, setJoinLink] = useState<JoinLink>();
  const [bonuses, setBonuses] = useState<Bonus[]>();
  const [bonusTypes, setBonusTypes] = useState<BonusTypeRow[]>([]);
  const [latestJobs, setLatestJobs] = useState<LatestLeagueJobs>({
    manual: null,
    cron: null,
  });
  const [poolTeams, setPoolTeams] = useState<Record<string, PoolTeam[]>>({});
  const [readiness, setReadiness] = useState<Readiness>();
  const [error, setError] = useState("");
  const [pollingJobId, setPollingJobId] = useState<UUID | null>(null);
  const toastedJobIds = useRef<Set<string>>(new Set());

  const load = useCallback(() => {
    setError("");
    const safe = <T,>(p: Promise<T>, fallback: T) => p.catch(() => fallback);
    return Promise.all([
      safe(api<Invite[]>(`/leagues/${league.id}/invites`), []),
      safe(api<JoinLink>(`/leagues/${league.id}/join-link`), {
        enabled: false,
        token: null,
        join_url: null,
      }),
      safe(api<Bonus[]>(`/leagues/${league.id}/manual-bonuses`), []),
      safe(api<BonusTypeRow[]>(`/leagues/${league.id}/bonus-types`), []),
      safe(api<LatestLeagueJobs>(`/leagues/${league.id}/jobs/latest`), {
        manual: null,
        cron: null,
      }),
      safe(api<Readiness>(`/leagues/${league.id}/readiness?purpose=sync`), {
        ready: false,
        checks: [
          {
            key: "load",
            label: "Could not load readiness",
            status: "error",
            detail: "Retry or check the API",
          },
        ],
        errors: ["Could not load readiness"],
        warnings: [],
      }),
      Promise.all(
        league.pools.map(async (p) =>
          [
            p.id,
            await safe(api<PoolTeam[]>(`/leagues/${league.id}/pools/${p.id}/teams`), []),
          ] as const,
        ),
      ),
    ])
      .then(([a, link, b, types, jobs, d, teams]) => {
        setInvites(a);
        setJoinLink(link);
        setBonuses(b);
        setBonusTypes(types);
        setLatestJobs(jobs);
        setReadiness(d);
        setPoolTeams(Object.fromEntries(teams));
        if (isActiveJob(jobs.manual)) {
          setPollingJobId(jobs.manual!.id);
        }
        return jobs;
      })
      .catch((e) => {
        setError(errorMessage(e));
        return null;
      });
  }, [league.id, league.pools]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!pollingJobId) return;
    let cancelled = false;

    const tick = async () => {
      try {
        const job = await api<LeagueJob>(`/leagues/${league.id}/jobs/${pollingJobId}`);
        if (cancelled) return;
        setLatestJobs((prev) => ({
          ...prev,
          manual: job.source === "commissioner" ? job : prev.manual,
        }));
        if (ACTIVE_JOB.has(job.status)) return;

        setPollingJobId(null);
        if (!toastedJobIds.current.has(job.id)) {
          toastedJobIds.current.add(job.id);
          const summary = summarizeJob(job);
          toast({
            message: summary,
            tone: job.status === "failed" ? "error" : "success",
            durationMs: summary.length > 120 ? null : 5000,
            dismissible: summary.length > 120 ? true : undefined,
          });
        }
        void load();
        onLeagueChange?.();
      } catch {
        /* keep polling; transient errors */
      }
    };

    void tick();
    const id = window.setInterval(() => void tick(), JOB_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollingJobId, league.id, load, onLeagueChange, toast]);

  async function action(
    path: string,
    method: string,
    body?: unknown,
    opts?: { quiet?: boolean },
  ) {
    try {
      const out = await api<Record<string, unknown>>(path, json(method, body));
      if (!opts?.quiet) {
        const summary = summarizeAction(out);
        const isLong = summary.length > 120;
        toast({
          message: summary,
          durationMs: isLong ? null : 4000,
          dismissible: isLong ? true : undefined,
        });
      }
      void load();
      onLeagueChange?.();
      return out;
    } catch (e) {
      toast({
        message: errorMessage(e),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    }
  }

  async function enqueueJob(kind: "sync" | "recompute") {
    const path =
      kind === "sync"
        ? `/leagues/${league.id}/sync`
        : `/leagues/${league.id}/recompute`;
    try {
      const job = await api<LeagueJob>(path, json("POST"));
      setLatestJobs((prev) => ({ ...prev, manual: job }));
      setPollingJobId(job.id);
      toast({
        message: kind === "sync" ? "Sync started in the background." : "Recompute started in the background.",
      });
      return job;
    } catch (e) {
      toast({
        message: errorMessage(e),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    }
  }

  const [joinLinkBusy, setJoinLinkBusy] = useState(false);

  async function updateJoinLink(body: { enabled?: boolean; rotate?: boolean }) {
    setJoinLinkBusy(true);
    const previous = joinLink;
    if (typeof body.enabled === "boolean") {
      setJoinLink((current) =>
        current
          ? { ...current, enabled: body.enabled! }
          : { enabled: body.enabled!, token: null, join_url: null },
      );
    }
    try {
      const out = await api<JoinLink>(`/leagues/${league.id}/join-link`, json("POST", body));
      setJoinLink(out);
      if (body.rotate) {
        toast({ message: "Join link rotated." });
      } else if (out.enabled) {
        toast({ message: "Join link ready." });
      } else {
        toast({ message: "Join link disabled." });
      }
      return out;
    } catch (e) {
      setJoinLink(previous);
      toast({
        message: errorMessage(e),
        tone: "error",
        durationMs: 6000,
        dismissible: true,
      });
    } finally {
      setJoinLinkBusy(false);
    }
  }

  const jobBusy = isActiveJob(latestJobs.manual) || !!pollingJobId;

  return {
    invites,
    joinLink,
    joinLinkBusy,
    bonuses,
    bonusTypes,
    latestJobs,
    jobBusy,
    poolTeams,
    readiness,
    error,
    load,
    action,
    enqueueJob,
    updateJoinLink,
    toast,
  };
}

export function summarizeJob(job: LeagueJob): string {
  const label = job.kind === "recompute" ? "recompute" : "sync";
  const source = job.source === "cron" ? "Scheduled" : "Manual";
  const subject = `${source} ${label}`;

  if (job.status === "pending") return `${subject} queued.`;
  if (job.status === "running") return `${subject} running…`;
  if (job.status === "failed") {
    return job.error || `${subject} failed.`;
  }

  const parts = summaryParts(job.summary);
  if (parts.length) return `${subject} complete — ${parts.join(" · ")}`;
  return `${subject} complete.`;
}

function summaryParts(summary: Record<string, unknown> | null | undefined): string[] {
  if (!summary) return [];
  const parts: string[] = [];
  if (summary.created != null) parts.push(`${summary.created} created`);
  if (summary.updated != null) parts.push(`${summary.updated} updated`);
  if (summary.changed != null) parts.push(`${summary.changed} changed`);
  if (summary.scored != null) parts.push(`${summary.scored} scored`);
  if (summary.cascaded != null) parts.push(`${summary.cascaded} cascaded`);
  if (summary.finished_matches != null) parts.push(`${summary.finished_matches} finished`);
  if (summary.skipped_missing_teams != null) {
    parts.push(`${summary.skipped_missing_teams} skipped (missing clubs)`);
  }
  return parts;
}

function summarizeAction(out: Record<string, unknown> | undefined): string {
  if (!out) return "Saved.";
  if (typeof out.detail === "string") return out.detail;
  if (typeof out.email === "string" && typeof out.email_sent === "boolean") {
    if (out.email_sent) return `Invite emailed to ${out.email}.`;
    const err = typeof out.email_error === "string" ? out.email_error : "email not sent";
    const url = typeof out.accept_url === "string" ? out.accept_url : "";
    return url
      ? `Invite created but email failed (${err}). Link: ${url}`
      : `Invite created but email failed (${err}).`;
  }
  if (typeof out.join_url === "string" || typeof out.enabled === "boolean") {
    if (out.enabled && typeof out.join_url === "string") {
      return `Join link ready: ${out.join_url}`;
    }
    if (out.enabled === false) return "Join link disabled.";
  }
  const parts = summaryParts(out);
  if (out.linked != null) parts.unshift(`${out.linked} linked`);
  if (out.created_teams != null) parts.push(`${out.created_teams} created`);
  if (out.skipped_existing != null) parts.push(`${out.skipped_existing} skipped`);
  if (out.ok === true && parts.length === 0) return "Sync complete.";
  if (parts.length) return parts.join(" · ");
  return "Saved.";
}
