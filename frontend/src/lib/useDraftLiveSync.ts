"use client";

import { useEffect, useRef, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { supabase } from "./supabase";

export type DraftRealtimeStatus = "connecting" | "subscribed" | "error" | "closed";

const POLL_MS_SUBSCRIBED = 5000;
const POLL_MS_FALLBACK = 2000;
const INVALIDATE_DEBOUNCE_MS = 150;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;

/**
 * Live draft sync: Supabase Realtime as the primary invalidate signal,
 * with adaptive HTTP polling as fallback / timer catch-up.
 *
 * Subscribes only to `draft_state` filtered by public_id. Picks/undo/open/complete
 * all update that row, so we avoid unfiltered `draft_picks` DELETE fan-out.
 */
export function useDraftLiveSync({
  leagueId,
  draftStatePublicId,
  enabled,
  onInvalidate,
}: {
  leagueId: string | null | undefined;
  /** DraftState.public_id from API — required to scope Realtime to this league. */
  draftStatePublicId: string | null | undefined;
  enabled: boolean;
  onInvalidate: () => void;
}): { realtimeStatus: DraftRealtimeStatus } {
  const [realtimeStatus, setRealtimeStatus] = useState<DraftRealtimeStatus>("closed");
  const onInvalidateRef = useRef(onInvalidate);
  onInvalidateRef.current = onInvalidate;
  const realtimeStatusRef = useRef<DraftRealtimeStatus>("closed");

  useEffect(() => {
    realtimeStatusRef.current = realtimeStatus;
  }, [realtimeStatus]);

  useEffect(() => {
    if (!enabled || !leagueId) {
      setRealtimeStatus("closed");
      return;
    }

    let cancelled = false;
    let channel: RealtimeChannel | null = null;
    let debounceTimer: number | null = null;
    let pollTimer: number | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempt = 0;

    const fire = () => {
      if (cancelled) return;
      if (document.visibilityState === "hidden") return;
      onInvalidateRef.current();
    };

    const scheduleInvalidate = () => {
      if (cancelled) return;
      if (debounceTimer != null) window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(() => {
        debounceTimer = null;
        fire();
      }, INVALIDATE_DEBOUNCE_MS);
    };

    const clearPoll = () => {
      if (pollTimer != null) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    };

    const clearReconnect = () => {
      if (reconnectTimer != null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const startPoll = () => {
      clearPoll();
      const ms =
        realtimeStatusRef.current === "subscribed"
          ? POLL_MS_SUBSCRIBED
          : POLL_MS_FALLBACK;
      pollTimer = window.setInterval(() => {
        if (document.visibilityState === "hidden") return;
        onInvalidateRef.current();
      }, ms);
    };

    const canSubscribeRealtime = Boolean(draftStatePublicId);

    const tearDownChannel = () => {
      if (channel) {
        void supabase().removeChannel(channel);
        channel = null;
      }
    };

    const subscribeRealtime = () => {
      if (cancelled || !draftStatePublicId) return;
      tearDownChannel();
      setRealtimeStatus("connecting");
      realtimeStatusRef.current = "connecting";

      try {
        channel = supabase()
          .channel(`draft:${leagueId}`)
          .on(
            "postgres_changes",
            {
              event: "*",
              schema: "public",
              table: "draft_state",
              filter: `public_id=eq.${draftStatePublicId}`,
            },
            () => scheduleInvalidate(),
          )
          .subscribe((status: string) => {
            if (cancelled) return;
            if (status === "SUBSCRIBED") {
              reconnectAttempt = 0;
              setRealtimeStatus("subscribed");
              realtimeStatusRef.current = "subscribed";
              startPoll();
            } else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
              setRealtimeStatus("error");
              realtimeStatusRef.current = "error";
              startPoll();
              scheduleReconnect();
            } else if (status === "CLOSED") {
              setRealtimeStatus("closed");
              realtimeStatusRef.current = "closed";
              startPoll();
              scheduleReconnect();
            }
          });
      } catch {
        if (!cancelled) {
          setRealtimeStatus("error");
          realtimeStatusRef.current = "error";
          startPoll();
          scheduleReconnect();
        }
      }
    };

    const scheduleReconnect = () => {
      if (cancelled || !canSubscribeRealtime) return;
      clearReconnect();
      const delay = Math.min(
        RECONNECT_MAX_MS,
        RECONNECT_BASE_MS * 2 ** Math.min(reconnectAttempt, 5),
      );
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        if (cancelled) return;
        subscribeRealtime();
      }, delay);
    };

    if (canSubscribeRealtime) {
      subscribeRealtime();
    } else {
      setRealtimeStatus("closed");
      realtimeStatusRef.current = "closed";
    }

    startPoll();
    // Initial catch-up in case we mounted mid-change.
    fire();

    const onVisibility = () => {
      if (document.visibilityState === "visible") fire();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (debounceTimer != null) window.clearTimeout(debounceTimer);
      clearPoll();
      clearReconnect();
      tearDownChannel();
      setRealtimeStatus("closed");
      realtimeStatusRef.current = "closed";
    };
  }, [enabled, leagueId, draftStatePublicId]);

  return { realtimeStatus };
}
