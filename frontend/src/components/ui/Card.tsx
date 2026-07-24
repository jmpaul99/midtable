import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Card({
  className,
  children,
  inset,
  ...props
}: HTMLAttributes<HTMLElement> & { inset?: boolean; children?: ReactNode }) {
  return (
    <section
      className={cn(
        "rounded-xl border border-line bg-surface shadow-soft",
        inset ? "bg-surface-2 p-3.5 shadow-none" : "p-4 sm:p-5",
        className,
      )}
      {...props}
    >
      {children}
    </section>
  );
}

export function Stack({
  className,
  children,
  gap = "md",
}: {
  className?: string;
  children?: ReactNode;
  gap?: "sm" | "md" | "lg";
}) {
  return (
    <div
      className={cn(
        "flex flex-col",
        gap === "sm" && "gap-3",
        gap === "md" && "gap-4",
        gap === "lg" && "gap-6",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Row({
  className,
  children,
  between,
}: {
  className?: string;
  children?: ReactNode;
  between?: boolean;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", between && "justify-between", className)}>
      {children}
    </div>
  );
}

export function Eyebrow({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <p className={cn("mb-1 text-xs font-extrabold uppercase tracking-[0.12em] text-brand", className)}>
      {children}
    </p>
  );
}

export function Muted({ children, className }: { children?: ReactNode; className?: string }) {
  return <p className={cn("text-sm text-muted", className)}>{children}</p>;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        <h1 className="truncate">{title}</h1>
        {description && <Muted className="mt-1">{description}</Muted>}
      </div>
      {actions && <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">{actions}</div>}
    </header>
  );
}

export function RankBadge({
  value,
  first,
  className,
}: {
  value: ReactNode;
  first?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "grid size-9 shrink-0 place-items-center rounded-lg text-sm font-extrabold",
        first ? "bg-accent text-on-accent" : "bg-surface-2 text-ink",
        className,
      )}
    >
      {value}
    </span>
  );
}

/** Compact metric tile — sized for 2-col phones, expands on larger screens. */
export function StatTile({
  label,
  value,
  hint,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  className?: string;
}) {
  return (
    <Card inset className={cn("min-w-0 p-3 sm:p-3.5", className)}>
      <Eyebrow className="mb-0.5 truncate">{label}</Eyebrow>
      <div className="truncate font-display text-xl font-extrabold leading-none tabular-nums sm:text-2xl md:text-3xl">
        {value}
      </div>
      {hint != null && hint !== false && (
        <Muted className="mt-1 truncate text-xs tabular-nums">{hint}</Muted>
      )}
    </Card>
  );
}

/** Responsive grid for StatTile rows (2 → 3 → 6). */
export function StatGrid({
  children,
  className,
}: {
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 lg:grid-cols-6",
        className,
      )}
    >
      {children}
    </div>
  );
}
