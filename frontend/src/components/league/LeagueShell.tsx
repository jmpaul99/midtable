"use client";

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
import { LeagueNav } from "@/components/Nav";
import { ErrorState, Loading, Status } from "@/components/ui/State";
import { Eyebrow, Row, Stack } from "@/components/ui/Card";

export type LeagueContextValue = {
  league: League;
  reload: () => void;
  isCommissioner: boolean;
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
  const abortRef = useRef<AbortController | null>(null);

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

  // Poll draft clock while drafting so the Draft nav can highlight on your turn.
  useEffect(() => {
    if (!league || league.status !== "drafting" || !league.current_member_id) {
      setOnTheClock(false);
      return;
    }

    let cancelled = false;
    const memberId = league.current_member_id;

    const check = (signal?: AbortSignal) => {
      if (document.visibilityState === "hidden") return;
      api<DraftState>(`/leagues/${league.id}/draft`, { signal })
        .then((draft) => {
          if (cancelled) return;
          const onClock = draft.current_member_id || draft.on_clock_member_id || null;
          const running = ["running", "open"].includes(draft.status);
          setOnTheClock(Boolean(running && onClock === memberId));
        })
        .catch((e) => {
          if (cancelled || (e as Error)?.name === "AbortError") return;
        });
    };

    const controller = new AbortController();
    check(controller.signal);
    const id = window.setInterval(() => check(), 2500);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(id);
    };
  }, [league?.id, league?.status, league?.current_member_id]);

  const isCommissioner = league?.role === "owner" || league?.role === "commissioner";

  const value = useMemo(
    () =>
      league
        ? {
            league,
            reload,
            isCommissioner: Boolean(isCommissioner),
          }
        : null,
    [league, reload, isCommissioner],
  );

  return (
    <RequireAuth>
      {!league && !error ? (
        <Loading label="Opening league" />
      ) : error && !league ? (
        <ErrorState error={error} retry={reload} />
      ) : league && value ? (
        <LeagueContext.Provider value={value}>
          <Stack gap="lg" className="animate-in pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:pb-0">
            {error && <ErrorState error={error} retry={reload} />}
            <header className="min-w-0">
              <Row className="gap-2">
                <Eyebrow className="mb-0">{league.season_label}</Eyebrow>
                <Status value={league.status} />
              </Row>
              <h1 className="mt-1 truncate">{league.name}</h1>
            </header>
            <LeagueNav
              leagueId={league.id}
              role={league.role}
              status={league.status}
              onTheClock={onTheClock}
            />
            <div className="animate-in">{children}</div>
          </Stack>
        </LeagueContext.Provider>
      ) : null}
    </RequireAuth>
  );
}
