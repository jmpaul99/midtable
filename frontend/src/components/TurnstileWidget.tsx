"use client";

import { useEffect, useRef, useState } from "react";
import Script from "next/script";

declare global {
  interface Window {
    turnstile?: {
      render: (
        el: HTMLElement,
        options: {
          sitekey: string;
          action?: string;
          callback?: (token: string) => void;
          "expired-callback"?: () => void;
          "error-callback"?: () => void;
        },
      ) => string;
      reset: (widgetId?: string) => void;
      remove: (widgetId?: string) => void;
    };
  }
}

type Props = {
  action: string;
  onToken: (token: string | null) => void;
  onWidgetId?: (widgetId: string | null) => void;
};

const SITEKEY = process.env.NEXT_PUBLIC_TURNSTILE_SITEKEY || "";
const LOAD_TIMEOUT_MS = 12_000;
const LOAD_ERROR =
  "Verification failed to load. Check your connection and try again.";

export function TurnstileWidget({ action, onToken, onWidgetId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  const onTokenRef = useRef(onToken);
  const onWidgetIdRef = useRef(onWidgetId);
  const pollRef = useRef<number | undefined>(undefined);
  const timeoutRef = useRef<number | undefined>(undefined);
  onTokenRef.current = onToken;
  onWidgetIdRef.current = onWidgetId;

  const [loadError, setLoadError] = useState<string | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);

  useEffect(() => {
    if (!SITEKEY || !containerRef.current) return;

    let cancelled = false;
    setLoadError(null);

    function clearTimers() {
      if (timeoutRef.current !== undefined) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = undefined;
      }
      if (pollRef.current !== undefined) {
        window.clearInterval(pollRef.current);
        pollRef.current = undefined;
      }
    }

    function cleanupWidget() {
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = null;
        onWidgetIdRef.current?.(null);
      }
    }

    function mount() {
      if (cancelled || !containerRef.current || !window.turnstile) return;
      cleanupWidget();
      const id = window.turnstile.render(containerRef.current, {
        sitekey: SITEKEY,
        action,
        callback: (token) => onTokenRef.current(token),
        "expired-callback": () => onTokenRef.current(null),
        "error-callback": () => onTokenRef.current(null),
      });
      widgetIdRef.current = id;
      onWidgetIdRef.current?.(id);
    }

    function giveUp() {
      if (cancelled) return;
      clearTimers();
      cleanupWidget();
      onTokenRef.current(null);
      setLoadError(LOAD_ERROR);
    }

    function tryMount() {
      if (cancelled || !window.turnstile) return false;
      clearTimers();
      mount();
      return true;
    }

    timeoutRef.current = window.setTimeout(giveUp, LOAD_TIMEOUT_MS);

    if (!tryMount()) {
      pollRef.current = window.setInterval(() => {
        tryMount();
      }, 50);
    }

    return () => {
      cancelled = true;
      clearTimers();
      cleanupWidget();
    };
  }, [action, retryNonce]);

  function failLoad() {
    if (timeoutRef.current !== undefined) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = undefined;
    }
    if (pollRef.current !== undefined) {
      window.clearInterval(pollRef.current);
      pollRef.current = undefined;
    }
    onToken(null);
    setLoadError(LOAD_ERROR);
  }

  function retry() {
    onToken(null);
    setLoadError(null);
    setRetryNonce((n) => n + 1);
  }

  if (!SITEKEY) {
    return (
      <p className="text-sm text-muted">
        Turnstile is not configured (NEXT_PUBLIC_TURNSTILE_SITEKEY).
      </p>
    );
  }

  return (
    <>
      <Script
        key={retryNonce}
        src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
        strategy="afterInteractive"
        onError={failLoad}
      />
      <div
        ref={containerRef}
        className={loadError ? "hidden" : "min-h-[65px]"}
        aria-hidden={loadError ? true : undefined}
      />
      {loadError && (
        <div className="flex flex-col gap-1.5">
          <p className="text-sm text-danger">{loadError}</p>
          <button
            type="button"
            onClick={retry}
            className="self-start text-sm font-semibold text-brand hover:underline"
          >
            Retry verification
          </button>
        </div>
      )}
    </>
  );
}

export function resetTurnstile(widgetId: string | null | undefined) {
  if (widgetId && window.turnstile) {
    window.turnstile.reset(widgetId);
  }
}
