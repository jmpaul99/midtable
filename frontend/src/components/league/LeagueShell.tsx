"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { RequireAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import type { DraftState, League } from "@/lib/types";
import { normalizeLeague } from "@/lib/types";
import { useDraftLiveSync } from "@/lib/useDraftLiveSync";
import { LeagueNav } from "@/components/Nav";
import { ErrorState, Loading, Status } from "@/components/ui/State";
import { Eyebrow, Row, Stack } from "@/components/ui/Card";
import { DraftStartCountdown } from "./DraftStartCountdown";

export type DraftInvalidateListener = (draft: DraftState) => void;

export type LeagueContextValue = {
  league: League;
  reload: () => void;
  isCommissioner: boolean;
  /** Single league-scoped draft live-sync; DraftBoard should subscribe instead of polling. */
  subscribeDraftInvalidate: (listener: DraftInvalidateListener) => () => void;
};

const LeagueContext = createContext<LeagueContextValue | null>(null);

export function useLeague(): League {
  return useLeagueContext().league;
}

export function useLeagueContext(): LeagueContextValue {
  const ctx = useContext(LeagueContext);
  if (!ctx) {
    throw new Error("useLeagueContext must be used within LeagueShell");
  }
  return ctx;
}

export function LeagueShell({
  leagueId,
  children,
}: {
  leagueId: string;
  children: ReactNode;
}) {
  const [league, setLeague] = useState<League>();
  const [error, setError] = useState("");
  const [onTheClock, setOnTheClock] = useState(false);
  const [draftStatePublicId, setDraftStatePublicId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const draftListenersRef = useRef(new Set<DraftInvalidateListener>());
  const draftSyncGenRef = useRef(0);
  const draftSyncInflightRef = useRef(false);
  const draftSyncQueuedRef = useRef(false);
  const draftDeadlineTimerRef = useRef<number | null>(null);
  const leagueStatusRef = useRef<string | undefined>(undefined);
  const memberIdRef = useRef<string | null | undefined>(undefined);
  const syncDraftRef = useRef<() => void>(() => {});

  const load = useCallback(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError("");
    api<League>(`/leagues/${leagueId}`, { signal: controller.signal })
      .then((raw) => {
        if (!controller.signal.aborted) setLeague(normalizeLeague(raw));
      })
      .catch((e) => {
        if (controller.signal.aborted || (e as Error)?.name === "AbortError") return;
        setError(errorMessage(e));
      });
    return () => {
      controller.abort();
      if (abortRef.current === controller) abortRef.current = null;
    };
  }, [leagueId]);

  const reload = useCallback(() => {
    load();
  }, [load]);

  useEffect(() => {
    return load();
  }, [load]);

  leagueStatusRef.current = league?.status;
  memberIdRef.current = league?.current_member_id;

  const liveSyncEnabled =
    Boolean(league) &&
    (league?.status === "pre_draft" || league?.status === "drafting");
  const leaguePublicId = league?.id;

  const subscribeDraftInvalidate = useCallback((listener: DraftInvalidateListener) => {
    draftListenersRef.current.add(listener);
    return () => {
      draftListenersRef.current.delete(listener);
    };
  }, []);

  const clearDeadlineTimer = useCallback(() => {
    if (draftDeadlineTimerRef.current != null) {
      window.clearTimeout(draftDeadlineTimerRef.current);
      draftDeadlineTimerRef.current = null;
    }
  }, []);

  const scheduleDeadlineSync = useCallback((deadlineAt: string | null | undefined) => {
    clearDeadlineTimer();
    if (!deadlineAt) return;
    const ms = new Date(deadlineAt).getTime() - Date.now();
    // Already expired: do not reschedule (avoids a tight loop). The timer set while
    // the deadline was still in the future fires once at expiry.
    if (ms <= 0) return;
    // Ignore absurd future deadlines (misconfigured clocks) — poll covers those.
    if (ms > 30 * 60_000) return;
    draftDeadlineTimerRef.current = window.setTimeout(() => {
      draftDeadlineTimerRef.current = null;
      syncDraftRef.current();
    }, ms + 75);
  }, [clearDeadlineTimer]);

  const syncDraft = useCallback(() => {
    if (!leaguePublicId) return;
    if (document.visibilityState === "hidden") return;
    // Coalesce overlapping polls: one in-flight GET, queue at most one follow-up.
    // Without this, 5s polls during slow/contended autopick pile up on the server.
    if (draftSyncInflightRef.current) {
      draftSyncQueuedRef.current = true;
      return;
    }
    draftSyncInflightRef.current = true;
    const gen = ++draftSyncGenRef.current;
    const expectedMemberId = memberIdRef.current;
    const expectedStatus = leagueStatusRef.current;
    api<DraftState>(`/leagues/${leaguePublicId}/draft`)
      .then((draft) => {
        if (gen !== draftSyncGenRef.current) return;
        setDraftStatePublicId(draft.id);
        const onClock = draft.current_member_id || draft.on_clock_member_id || null;
        const running = ["running", "open"].includes(draft.status);
        setOnTheClock(Boolean(running && expectedMemberId && onClock === expectedMemberId));
        if (draft.league_status && expectedStatus && draft.league_status !== expectedStatus) {
          reload();
        }
        scheduleDeadlineSync(running ? draft.pick_deadline_at : null);
        draftListenersRef.current.forEach((listener) => listener(draft));
      })
      .catch((e) => {
        if (gen !== draftSyncGenRef.current) return;
        if ((e as Error)?.name === "AbortError") return;
      })
      .finally(() => {
        if (gen !== draftSyncGenRef.current) return;
        draftSyncInflightRef.current = false;
        if (draftSyncQueuedRef.current) {
          draftSyncQueuedRef.current = false;
          syncDraftRef.current();
        }
      });
  }, [leaguePublicId, reload, scheduleDeadlineSync]);

  syncDraftRef.current = syncDraft;

  useEffect(() => {
    if (!liveSyncEnabled) {
      setOnTheClock(false);
      setDraftStatePublicId(null);
      clearDeadlineTimer();
    }
  }, [liveSyncEnabled, clearDeadlineTimer]);

  useEffect(() => {
    return () => {
      draftSyncGenRef.current += 1;
      draftSyncInflightRef.current = false;
      draftSyncQueuedRef.current = false;
      clearDeadlineTimer();
    };
  }, [leaguePublicId, clearDeadlineTimer]);

  useDraftLiveSync({
    leagueId: leaguePublicId,
    draftStatePublicId,
    enabled: liveSyncEnabled,
    onInvalidate: syncDraft,
  });

  const isCommissioner = league?.role === "owner" || league?.role === "commissioner";
  const pathname = usePathname();
  const onSettingsPage = pathname?.includes(`/leagues/${leagueId}/settings`) ?? false;
  const draftScheduledAt =
    league?.draft_scheduled_at ??
    (typeof league?.settings?.draft_scheduled_at === "string"
      ? league.settings.draft_scheduled_at
      : null);

  const value = useMemo(
    () =>
      league
        ? {
            league,
            reload,
            isCommissioner: Boolean(isCommissioner),
            subscribeDraftInvalidate,
          }
        : null,
    [league, reload, isCommissioner, subscribeDraftInvalidate],
  );

  return (
    <RequireAuth>
      {!league && !error ? (
        <Loading label="Opening league" />
      ) : error && !league ? (
        <ErrorState error={error} retry={reload} />
      ) : value ? (
        <LeagueContext.Provider value={value}>
          <Stack gap="lg" className="min-w-0 animate-in pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:pb-0">
            {error && <ErrorState error={error} retry={reload} />}
            <header className="min-w-0">
              <Row className="gap-2">
                <Eyebrow className="mb-0">{value.league.season_label}</Eyebrow>
                <Status value={value.league.status} />
              </Row>
              <h1 className="mt-1 truncate">
                <Link
                  href={`/leagues/${value.league.id}`}
                  className="hover:underline focus-visible:underline"
                >
                  {value.league.name}
                </Link>
              </h1>
              {!onSettingsPage && (
                <Link
                  href={`/leagues/${value.league.id}/settings`}
                  className="mt-1.5 inline-flex text-sm font-semibold text-muted hover:text-ink"
                >
                  View rules & settings →
                </Link>
              )}
            </header>
            {value.league.status === "pre_draft" && draftScheduledAt ? (
              <DraftStartCountdown scheduledAt={draftScheduledAt} />
            ) : null}
            <LeagueNav
              leagueId={value.league.id}
              role={value.league.role}
              status={value.league.status}
              onTheClock={onTheClock}
            />
            <div className="min-w-0 animate-in">{children}</div>
          </Stack>
        </LeagueContext.Provider>
      ) : null}
    </RequireAuth>
  );
}
