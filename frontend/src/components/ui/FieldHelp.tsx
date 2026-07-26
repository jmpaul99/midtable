"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export function FieldHelp({
  label,
  children,
  className,
}: {
  /** Short name used in the button aria-label */
  label: string;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <span ref={rootRef} className={cn("relative inline-flex align-middle", className)}>
      <button
        type="button"
        className="inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-line bg-surface text-[11px] font-bold text-muted transition hover:border-brand/40 hover:text-ink"
        aria-label={`About ${label}`}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        ?
      </button>
      {open && (
        <span
          id={panelId}
          role="note"
          className="absolute left-0 top-[calc(100%+0.35rem)] z-30 w-[min(18rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-3 text-xs font-normal leading-relaxed text-muted shadow-soft"
        >
          {children}
        </span>
      )}
    </span>
  );
}

export function LabelRow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm font-semibold text-muted", className)}>
      {children}
    </span>
  );
}
