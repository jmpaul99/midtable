"use client";

import type { ReactNode } from "react";
import { IconButton } from "@/components/ui/IconButton";
import { XIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";

export type ToastTone = "info" | "error" | "success";

export function ToastPill({
  children,
  tone = "success",
  dismissible = false,
  onDismiss,
  className,
}: {
  children: ReactNode;
  tone?: ToastTone;
  dismissible?: boolean;
  onDismiss?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "pointer-events-auto flex max-w-sm items-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold text-ink shadow-soft animate-in",
        tone === "info" && "border-brand/30 bg-surface",
        tone === "error" && "border-danger/30 bg-surface",
        tone === "success" && "border-brand/40 bg-surface",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <span
        className={cn(
          "size-2 shrink-0 rounded-full",
          tone === "info" && "bg-brand",
          tone === "error" && "bg-danger",
          tone === "success" && "bg-accent",
        )}
        aria-hidden
      />
      <div className="min-w-0 flex-1">{children}</div>
      {dismissible && (
        <IconButton
          type="button"
          variant="ghost"
          size="icon-sm"
          label="Dismiss"
          className="shrink-0"
          onClick={onDismiss}
        >
          <XIcon className="size-4" />
        </IconButton>
      )}
    </div>
  );
}
