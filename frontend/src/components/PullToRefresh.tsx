"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { RefreshIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";

const PULL_THRESHOLD = 72;
const MAX_PULL = 112;
const PULL_RESISTANCE = 0.45;

/** Matches the app `md` breakpoint — bottom nav / mobile chrome. */
const MOBILE_QUERY = "(max-width: 767px)";

function scrollTop(): number {
  return window.scrollY || document.documentElement.scrollTop || 0;
}

function isVerticallyScrollable(el: HTMLElement): boolean {
  const style = window.getComputedStyle(el);
  const overflowY = style.overflowY;
  if (overflowY !== "auto" && overflowY !== "scroll" && overflowY !== "overlay") return false;
  return el.scrollHeight > el.clientHeight + 1;
}

/** True when a nested scroll container above the document owns the gesture. */
function nestedScrollerBlocksPull(target: EventTarget | null): boolean {
  let el = target instanceof Element ? target : null;
  while (el && el !== document.body && el !== document.documentElement) {
    if (el instanceof HTMLElement && isVerticallyScrollable(el) && el.scrollTop > 0) {
      return true;
    }
    el = el.parentElement;
  }
  return false;
}

/** Open dialogs (incl. backdrops) should not trigger a full page reload. */
function modalBlocksPull(target: EventTarget | null): boolean {
  if (document.querySelector('[aria-modal="true"], [role="dialog"], [role="alertdialog"]')) {
    return true;
  }
  let el = target instanceof Element ? target : null;
  while (el && el !== document.body && el !== document.documentElement) {
    const role = el.getAttribute("role");
    if (el.getAttribute("aria-modal") === "true" || role === "dialog" || role === "alertdialog") {
      return true;
    }
    el = el.parentElement;
  }
  return false;
}

function shouldIgnorePull(target: EventTarget | null): boolean {
  return nestedScrollerBlocksPull(target) || modalBlocksPull(target);
}

export function PullToRefresh({ children }: { children: ReactNode }) {
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [mobile, setMobile] = useState(false);
  const startY = useRef<number | null>(null);
  const startX = useRef<number | null>(null);
  const pullRef = useRef(0);
  const refreshingRef = useRef(false);
  const armed = useRef(false);
  const horizontal = useRef(false);

  useEffect(() => {
    const media = window.matchMedia(MOBILE_QUERY);
    const syncMobile = () => setMobile(media.matches);
    syncMobile();
    media.addEventListener("change", syncMobile);
    return () => media.removeEventListener("change", syncMobile);
  }, []);

  useEffect(() => {
    if (!mobile) {
      pullRef.current = 0;
      setPull(0);
      return;
    }

    const setPullDistance = (value: number) => {
      pullRef.current = value;
      setPull(value);
    };

    const reset = () => {
      startY.current = null;
      startX.current = null;
      armed.current = false;
      horizontal.current = false;
      if (!refreshingRef.current) setPullDistance(0);
    };

    const onTouchStart = (event: TouchEvent) => {
      if (refreshingRef.current) return;
      if (event.touches.length !== 1) return;
      if (scrollTop() > 1) return;
      if (shouldIgnorePull(event.target)) return;

      const touch = event.touches[0];
      startY.current = touch.clientY;
      startX.current = touch.clientX;
      armed.current = false;
      horizontal.current = false;
    };

    const onTouchMove = (event: TouchEvent) => {
      if (refreshingRef.current) return;
      if (startY.current == null || startX.current == null) return;
      if (event.touches.length !== 1) {
        reset();
        return;
      }

      const touch = event.touches[0];
      const dy = touch.clientY - startY.current;
      const dx = touch.clientX - startX.current;

      if (!armed.current && !horizontal.current) {
        if (Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy)) {
          horizontal.current = true;
          setPullDistance(0);
          return;
        }
        if (dy > 8 && scrollTop() <= 1 && !shouldIgnorePull(event.target)) {
          armed.current = true;
        }
      }

      if (horizontal.current || !armed.current) return;

      if (scrollTop() > 1 || dy <= 0) {
        setPullDistance(0);
        return;
      }

      const distance = Math.min(MAX_PULL, dy * PULL_RESISTANCE);
      setPullDistance(distance);

      // Keep the indicator under finger control instead of rubber-banding the page.
      if (dy > 10 && event.cancelable) {
        event.preventDefault();
      }
    };

    const onTouchEnd = () => {
      if (refreshingRef.current) return;

      if (armed.current && pullRef.current >= PULL_THRESHOLD) {
        refreshingRef.current = true;
        setRefreshing(true);
        setPullDistance(PULL_THRESHOLD);
        window.location.reload();
        return;
      }

      reset();
    };

    // Document-level listeners so every route gets pull-to-refresh on mobile.
    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchmove", onTouchMove, { passive: false });
    document.addEventListener("touchend", onTouchEnd);
    document.addEventListener("touchcancel", onTouchEnd);

    return () => {
      document.removeEventListener("touchstart", onTouchStart);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
      document.removeEventListener("touchcancel", onTouchEnd);
    };
  }, [mobile]);

  const progress = Math.min(1, pull / PULL_THRESHOLD);
  const ready = pull >= PULL_THRESHOLD || refreshing;
  const visible = mobile && (pull > 4 || refreshing);

  return (
    <>
      <div
        className={cn(
          "pointer-events-none fixed inset-x-0 z-[60] flex justify-center md:hidden",
          "top-[max(0.75rem,env(safe-area-inset-top))]",
          "transition-[opacity,transform] duration-150 ease-out",
          visible ? "opacity-100" : "opacity-0",
        )}
        style={{ transform: `translateY(${Math.max(0, pull - 28)}px)` }}
        aria-hidden={!visible}
      >
        <div
          className={cn(
            "flex size-10 items-center justify-center rounded-full border border-line bg-surface text-brand shadow-soft",
            refreshing && "border-brand/40",
          )}
          role="status"
          aria-live="polite"
          aria-label={refreshing ? "Refreshing" : ready ? "Release to refresh" : "Pull to refresh"}
        >
          <RefreshIcon
            className={cn("size-5 transition-transform duration-150", refreshing && "animate-spin")}
            style={
              refreshing
                ? undefined
                : { transform: `rotate(${progress * 180}deg)`, opacity: 0.45 + progress * 0.55 }
            }
          />
        </div>
      </div>
      {children}
    </>
  );
}
