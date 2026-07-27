import type { ReactNode } from "react";
import { IconButton } from "@/components/ui/IconButton";
import { ChevronDownIcon, ChevronUpIcon, PlusIcon, TrashIcon } from "@/components/ui/icons";
import { Muted } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

export function EditorSection({
  title,
  description,
  children,
  className,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("flex flex-col gap-3", className)}>
      {(title || description) && (
        <div>
          {title ? <h3 className="font-display text-base font-extrabold">{title}</h3> : null}
          {description ? (
            <Muted className={cn("text-xs", title && "mt-0.5")}>{description}</Muted>
          ) : null}
        </div>
      )}
      {children}
    </section>
  );
}

export function RowList({ children }: { children: ReactNode }) {
  return (
    <ul className="divide-y divide-line rounded-xl border border-line [&_>li:first-child]:rounded-t-[calc(0.75rem-1px)] [&_>li:last-child]:rounded-b-[calc(0.75rem-1px)]">
      {children}
    </ul>
  );
}

export function RowItem({ children, className }: { children: ReactNode; className?: string }) {
  return <li className={cn("bg-surface-2/30 p-3", className)}>{children}</li>;
}

export function AddRowButton({
  label,
  onClick,
  className,
}: {
  label: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <div className={cn("flex justify-start", className)}>
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

/** Up/down controls for list display order. */
export function ReorderButtons({
  index,
  total,
  onMove,
  itemLabel = "item",
}: {
  index: number;
  total: number;
  onMove: (from: number, to: number) => void;
  itemLabel?: string;
}) {
  return (
    <div className="flex shrink-0 flex-col gap-1">
      <IconButton
        type="button"
        variant="secondary"
        size="icon-sm"
        label={`Move ${itemLabel} ${index + 1} up`}
        disabled={index === 0}
        onClick={() => onMove(index, index - 1)}
      >
        <ChevronUpIcon className="size-4" />
      </IconButton>
      <IconButton
        type="button"
        variant="secondary"
        size="icon-sm"
        label={`Move ${itemLabel} ${index + 1} down`}
        disabled={index >= total - 1}
        onClick={() => onMove(index, index + 1)}
      >
        <ChevronDownIcon className="size-4" />
      </IconButton>
    </div>
  );
}

/** Compact field chrome for dense editor grids. */
export const compactField =
  "min-h-11 rounded-lg border border-line bg-surface px-2.5 py-2 text-sm text-ink";
