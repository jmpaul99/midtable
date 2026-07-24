import type { ReactNode } from "react";
import { IconButton } from "@/components/ui/IconButton";
import { PlusIcon, TrashIcon } from "@/components/ui/icons";
import { Muted } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

export function EditorSection({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("flex flex-col gap-3", className)}>
      <div>
        <h3 className="font-display text-base font-extrabold">{title}</h3>
        {description ? <Muted className="mt-0.5 text-xs">{description}</Muted> : null}
      </div>
      {children}
    </section>
  );
}

export function RowList({ children }: { children: ReactNode }) {
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line">{children}</ul>
  );
}

export function RowItem({ children, className }: { children: ReactNode; className?: string }) {
  return <li className={cn("bg-surface-2/30 p-3", className)}>{children}</li>;
}

export function AddRowButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <div className="flex justify-start">
      <IconButton type="button" label={label} variant="secondary" onClick={onClick}>
        <PlusIcon />
      </IconButton>
    </div>
  );
}

export function RemoveButton({
  onClick,
  label = "Remove",
}: {
  onClick: () => void;
  label?: string;
}) {
  return (
    <IconButton
      type="button"
      label={label}
      variant="ghost"
      size="icon-sm"
      className="text-danger hover:bg-danger/10 hover:text-danger"
      onClick={onClick}
    >
      <TrashIcon className="size-4" />
    </IconButton>
  );
}

/** Compact field chrome for dense editor grids. */
export const compactField =
  "min-h-11 rounded-lg border border-line bg-surface px-2.5 py-2 text-sm text-ink";
