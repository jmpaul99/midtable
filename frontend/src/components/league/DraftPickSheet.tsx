"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import { formatCountdownDuration } from "@/lib/format";
import type { AutopickPreview } from "@/lib/types";
import { ChevronDownIcon, ChevronUpIcon } from "@/components/ui/icons";

/**
 * Height of LeagueBottomNav: pt-1.5 (0.375rem) + min-h-12 (3rem) +
 * paddingBottom max(0.5rem, safe-area).
 */
const NAV_OFFSET =
  "calc(3.375rem + max(0.5rem, env(safe-area-inset-bottom, 0px)))";
const DRAG_THRESHOLD_PX = 40;

/** Extra bottom padding so the board clears the collapsed sheet (nav already padded by LeagueShell). */
export const DRAFT_PICK_SHEET_COLLAPSED_PAD = "pb-[4.5rem] lg:pb-0";

export function DraftPickSheet({
  yourTurn,
  deadlineAt,
  autopickPreview = null,
  children,
}: {
  yourTurn: boolean;
  deadlineAt?: string | null;
  autopickPreview?: AutopickPreview | null;
  children: ReactNode;
}) {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const panelId = useId();
  const dragRef = useRef<{
    pointerId: number;
    startY: number;
    moved: boolean;
  } | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!yourTurn || !deadlineAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [yourTurn, deadlineAt]);

  function endDrag(clientY: number) {
    const start = dragRef.current;
    dragRef.current = null;
    setDragging(false);
    setDragOffset(0);
    if (!start) return;

    const delta = start.startY - clientY;
    if (Math.abs(delta) < DRAG_THRESHOLD_PX) {
      if (!start.moved) setOpen((v) => !v);
      return;
    }
    if (delta > 0) setOpen(true);
    else setOpen(false);
  }

  function onPointerDown(e: ReactPointerEvent<HTMLButtonElement>) {
    if (e.button !== 0) return;
    dragRef.current = {
      pointerId: e.pointerId,
      startY: e.clientY,
      moved: false,
    };
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: ReactPointerEvent<HTMLButtonElement>) {
    const start = dragRef.current;
    if (!start || start.pointerId !== e.pointerId) return;
    const delta = start.startY - e.clientY;
    if (Math.abs(delta) > 4) start.moved = true;
    if (open) {
      setDragOffset(Math.min(0, delta));
    } else {
      setDragOffset(Math.max(0, delta));
    }
  }

  function onPointerUp(e: ReactPointerEvent<HTMLButtonElement>) {
    const start = dragRef.current;
    if (!start || start.pointerId !== e.pointerId) return;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* already released */
    }
    endDrag(e.clientY);
  }

  function onPointerCancel(e: ReactPointerEvent<HTMLButtonElement>) {
    const start = dragRef.current;
    if (!start || start.pointerId !== e.pointerId) return;
    dragRef.current = null;
    setDragging(false);
    setDragOffset(0);
  }

  if (!mounted || typeof document === "undefined") return null;

  const remainingMs =
    yourTurn && deadlineAt ? new Date(deadlineAt).getTime() - now : null;
  const timerLabel =
    remainingMs == null
      ? null
      : remainingMs <= 0
        ? "0:00"
        : formatCountdownDuration(remainingMs);
  const urgent = remainingMs != null && remainingMs < 15_000;

  const autopickBit =
    yourTurn && deadlineAt && autopickPreview
      ? autopickPreview.mode === "random" || !autopickPreview.team_name
        ? "Autopick a random club"
        : `Autopick ${autopickPreview.team_name}`
      : null;
  const label = yourTurn
    ? timerLabel
      ? remainingMs != null && remainingMs <= 0
        ? "Time’s up — auto-picking…"
        : autopickBit
          ? `You’re on the clock · ${timerLabel} · ${autopickBit}`
          : `You’re on the clock · ${timerLabel} — open to pick`
      : "You’re on the clock — open to make your pick"
    : "Available teams";

  return createPortal(
    <div
      className="pointer-events-none fixed inset-x-0 z-40 lg:hidden"
      style={{ bottom: NAV_OFFSET }}
    >
      <div
        className={cn(
          "pointer-events-auto mx-auto flex max-w-3xl flex-col overflow-hidden rounded-t-2xl border border-b-0 border-line bg-surface shadow-[0_-8px_24px_rgba(24,24,27,0.12)]",
          yourTurn &&
            "draft-on-clock-pulse bg-[color-mix(in_srgb,var(--color-brand)_10%,var(--color-surface))]",
          !dragging && open && "transition-[max-height] duration-200 ease-out",
        )}
        style={{
          maxHeight: open ? "min(65vh, 36rem)" : undefined,
          transform:
            dragOffset !== 0
              ? `translateY(${open ? Math.max(0, -dragOffset) * 0.15 : -Math.min(dragOffset, 80) * 0.2}px)`
              : undefined,
        }}
      >
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerCancel}
          className="flex w-full shrink-0 touch-none flex-col items-center gap-1 bg-inherit px-4 pb-2.5 pt-2 text-center"
        >
          <span className="flex flex-col items-center gap-0.5 text-muted" aria-hidden>
            <span className="h-1 w-10 rounded-full bg-line" />
            {open ? (
              <ChevronDownIcon className="size-4" />
            ) : (
              <ChevronUpIcon className="size-4" />
            )}
          </span>
          <span
            className={cn(
              "line-clamp-2 text-sm font-bold leading-snug",
              urgent ? "text-danger" : yourTurn ? "text-brand" : "text-ink",
            )}
          >
            {label}
          </span>
        </button>

        <div
          id={panelId}
          hidden={!open}
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-inherit px-3 pb-3"
        >
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
