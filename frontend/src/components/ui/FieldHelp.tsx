"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";

const PANEL_GAP = 6;
const PANEL_MAX_WIDTH = 288; // 18rem
const VIEWPORT_PAD = 8;

function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n));
}

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
  const [mounted, setMounted] = useState(false);
  const [panelStyle, setPanelStyle] = useState<CSSProperties | undefined>(undefined);
  const panelId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useLayoutEffect(() => {
    if (!open) {
      setPanelStyle(undefined);
      return;
    }

    function place() {
      const btn = buttonRef.current;
      if (!btn) return;

      const rect = btn.getBoundingClientRect();
      const width = Math.min(PANEL_MAX_WIDTH, window.innerWidth - VIEWPORT_PAD * 2);
      const panelHeight = panelRef.current?.offsetHeight ?? 0;

      let top = rect.bottom + PANEL_GAP;
      const spaceBelow = window.innerHeight - VIEWPORT_PAD - top;
      const spaceAbove = rect.top - PANEL_GAP - VIEWPORT_PAD;

      if (panelHeight > 0 && panelHeight > spaceBelow && spaceAbove > spaceBelow) {
        top = rect.top - PANEL_GAP - panelHeight;
      }

      top = clamp(top, VIEWPORT_PAD, window.innerHeight - VIEWPORT_PAD - Math.max(panelHeight, 1));

      let left = rect.left;
      left = clamp(left, VIEWPORT_PAD, window.innerWidth - VIEWPORT_PAD - width);

      setPanelStyle({
        position: "fixed",
        top,
        left,
        width,
        zIndex: 50,
      });
    }

    place();
    // Remeasure after paint so flip/clamp uses the real panel height.
    const raf = requestAnimationFrame(place);

    window.addEventListener("resize", place);
    // Capture scrolls from overflow ancestors that would otherwise clip inline panels.
    window.addEventListener("scroll", place, true);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, children]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      const target = e.target as Node;
      if (buttonRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      setOpen(false);
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
    <span className={cn("inline-flex align-middle", className)}>
      <button
        ref={buttonRef}
        type="button"
        className="inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-line bg-surface text-[11px] font-bold text-muted transition hover:border-brand/40 hover:text-ink"
        aria-label={`About ${label}`}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        ?
      </button>
      {mounted &&
        open &&
        createPortal(
          <span
            ref={panelRef}
            id={panelId}
            role="note"
            style={panelStyle}
            className="rounded-xl border border-line bg-surface p-3 text-xs font-normal leading-relaxed text-muted shadow-soft"
          >
            {children}
          </span>,
          document.body,
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
