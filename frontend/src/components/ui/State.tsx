"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { IconButton } from "./IconButton";
import { RefreshIcon } from "./icons";

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="grid min-h-32 place-items-center rounded-xl border border-dashed border-line bg-surface/60 p-6" role="status">
      <div className="flex flex-col items-center gap-3 text-muted">
        <span className="size-8 animate-spin rounded-full border-2 border-line border-t-brand" aria-hidden />
        <span className="text-sm font-semibold">{label}…</span>
      </div>
    </div>
  );
}

export function ErrorState({ error, retry }: { error: string; retry?: () => void }) {
  return (
    <div className="rounded-xl border border-danger/20 bg-danger/10 p-4 text-ink" role="alert">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-sm font-medium">{error}</span>
        {retry && (
          <IconButton type="button" variant="secondary" label="Try again" onClick={retry}>
            <RefreshIcon />
          </IconButton>
        )}
      </div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-surface/70 px-4 py-10 text-center">
      <h3 className="text-lg font-extrabold">{title}</h3>
      {children && <div className="mt-2 text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Status({ value }: { value: string }) {
  const good = ["active", "ready", "succeeded", "complete", "completed", "locked", "running", "ok"].includes(
    value.toLowerCase(),
  );
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-bold capitalize text-ink">
      <i
        className={cn("size-2 rounded-full", good ? "bg-brand" : "bg-warning")}
        aria-hidden
      />
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function StatusBanner({
  children,
  tone = "info",
  className,
}: {
  children: ReactNode;
  tone?: "info" | "error" | "success";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border-l-4 px-4 py-3 text-sm",
        tone === "info" && "border-brand bg-brand/10",
        tone === "error" && "border-danger bg-danger/10",
        tone === "success" && "border-brand bg-accent/30",
        className,
      )}
      role="status"
    >
      {children}
    </div>
  );
}
