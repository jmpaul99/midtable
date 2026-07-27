"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, json } from "@/lib/api";
import type {
  Bonus,
  Invite,
  JoinLink,
  League,
  PoolTeam,
  Readiness,
  SyncStatus,
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

export function useAdminLeagueData(league: League, onLeagueChange?: () => void) {
  const { toast } = useToast();
  const [invites, setInvites] = useState<Invite[]>();
  const [joinLink, setJoinLink] = useState<JoinLink>();
  const [bonuses, setBonuses] = useState<Bonus[]>();
  const [bonusTypes, setBonusTypes] = useState<BonusTypeRow[]>([]);
  const [sync, setSync] = useState<SyncStatus[]>();
  const [poolTeams, setPoolTeams] = useState<Record<string, PoolTeam[]>>({});
  const [readiness, setReadiness] = useState<Readiness>();
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    const safe = <T,>(p: Promise<T>, fallback: T) => p.catch(() => fallback);
    Promise.all([
      safe(api<Invite[]>(`/leagues/${league.id}/invites`), []),
      safe(api<JoinLink>(`/leagues/${league.id}/join-link`), {
        enabled: false,
        token: null,
        join_url: null,
      }),
      safe(api<Bonus[]>(`/leagues/${league.id}/manual-bonuses`), []),
      safe(api<BonusTypeRow[]>(`/leagues/${league.id}/bonus-types`), []),
      safe(api<SyncStatus[]>(`/leagues/${league.id}/sync-status`), []),
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
      .then(([a, link, b, types, c, d, teams]) => {
        setInvites(a);
        setJoinLink(link);
        setBonuses(b);
        setBonusTypes(types);
        setSync(c);
        setReadiness(d);
        setPoolTeams(Object.fromEntries(teams));
      })
      .catch((e) => setError(errorMessage(e)));
  }, [league.id, league.pools]);

  useEffect(() => {
    load();
  }, [load]);

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
      load();
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

  return {
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
  };
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
  const parts: string[] = [];
  if (out.linked != null) parts.push(`${out.linked} linked`);
  if (out.created_teams != null) parts.push(`${out.created_teams} created`);
  if (out.skipped_existing != null) parts.push(`${out.skipped_existing} skipped`);
  if (out.scored != null) parts.push(`${out.scored} scored`);
  if (out.cascaded != null) parts.push(`${out.cascaded} cascaded`);
  if (out.finished_matches != null) parts.push(`${out.finished_matches} finished`);
  if (out.ok === true && parts.length === 0) return "Sync complete.";
  if (parts.length) return parts.join(" · ");
  return "Saved.";
}
